import json
import time
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.parse import urlparse
import requests

TZ = ZoneInfo('Asia/Shanghai')
SESSION = requests.Session()
SESSION.headers.update({'User-Agent':'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131.0 Safari/537.36','Accept':'application/json,text/plain,*/*','Referer':'https://xuangutong.com.cn/'})

class FetchError(Exception): pass

def get_json(url, params=None):
    last = None
    for attempt in range(3):
        try:
            r = SESSION.get(url,params=params,timeout=18)
            r.raise_for_status()
            obj = r.json()
            if not isinstance(obj,dict): raise ValueError('non-object JSON')
            return obj
        except (requests.RequestException, ValueError) as e:
            last = e
            if attempt < 2: time.sleep(2*(attempt+1))
    raise FetchError(f'{urlparse(url).netloc}: {last}')

def market_date():
    obj=get_json('https://api-ddc-wscn.xuangubao.com.cn/market/trend',{'fields':'tick_at,close_px','prod_code':'000001.SS'})
    lines=obj['data']['candle']['000001.SS']['lines']
    if not isinstance(lines,list) or not lines or not isinstance(lines[-1],list): raise FetchError('上证指数日线结构异常')
    return datetime.fromtimestamp(float(lines[-1][0]),TZ).date()

def rank_ids(typ):
    obj=get_json('https://flash-api.xuangubao.com.cn/api/plate/rank',{'field':'core_avg_pcp','type':typ})
    data=obj.get('data')
    if not isinstance(data,list) or len(data)<3: raise FetchError(f'板块rank type={typ} 返回不足3个ID或结构异常')
    return [str(v) for v in data[:3]]

def plate_meta(ids):
    obj=get_json('https://flash-api.xuangubao.com.cn/api/plate/data',{'fields':'plate_id,plate_name,core_avg_pcp','plates':','.join(ids)})
    data=obj.get('data')
    if isinstance(data,list): records=data
    elif isinstance(data,dict): records=list(data.values())
    else: raise FetchError('plate/data结构异常')
    result={}
    for rec in records:
        if not isinstance(rec,dict): continue
        pid=str(rec.get('plate_id',''))
        if pid in ids: result[pid]=rec
    return result

def stock_symbols(pid):
    obj=get_json('https://flash-api.xuangubao.com.cn/api/plate/plate_set',{'id':pid,'display_premium_stock':'true'})
    stocks=obj['data']['stocks']
    if not isinstance(stocks,list): raise FetchError(f'板块{pid} stocks结构异常')
    symbols=[]
    for x in stocks:
        s=x.get('symbol') if isinstance(x,dict) else x
        if s: symbols.append(str(s))
    return list(dict.fromkeys(symbols))

def stock_quotes(symbols):
    all_rows=[]
    for start in range(0,len(symbols),50):
        obj=get_json('https://flash-api.xuangubao.com.cn/api/stock/data',{'symbols':','.join(symbols[start:start+50]),'fields':'symbol,stock_chi_name,change_percent,price','strict':'true'})
        data=obj.get('data')
        if isinstance(data,list): rows=data
        elif isinstance(data,dict): rows=list(data.values())
        else: raise FetchError('stock/data结构异常')
        all_rows.extend(x for x in rows if isinstance(x,dict))
    return all_rows

def collect_plates():
    tabs_ids={'行业板块':rank_ids(2),'概念板块':rank_ids(1),'风格板块':rank_ids(3)}
    ids=list(dict.fromkeys(sum(tabs_ids.values(),[])))
    meta=plate_meta(ids)
    tabs={}; errors=[]
    for tab, tab_ids in tabs_ids.items():
        tabs[tab]=[]
        for pid in tab_ids:
            rec=meta.get(pid)
            if not rec or not rec.get('plate_name') or rec.get('core_avg_pcp') is None:
                errors.append(f'{tab} {pid}: plate/data缺少名称或涨幅'); continue
            try:
                symbols=stock_symbols(pid)
                rows=stock_quotes(symbols)
                wanted=set(symbols); valid={}
                for row in rows:
                    try:
                        sym=str(row['symbol']); pct=float(row['change_percent']); price=float(row['price'])
                        if sym in wanted and row.get('stock_chi_name') and price>0:
                            valid[sym]={'name':str(row['stock_chi_name']),'symbol':sym,'change_percent':pct}
                    except (ValueError,TypeError,KeyError): continue
                top=sorted(valid.values(),key=lambda x:x['change_percent'],reverse=True)[:10]
                tabs[tab].append({'plate_id':pid,'plate_name':str(rec['plate_name']),'core_avg_pcp':float(rec['core_avg_pcp']),'top10_stocks':top,'constituent_count':len(symbols),'skipped_no_data':len(symbols)-len(valid)})
            except (FetchError,KeyError,TypeError,ValueError) as e:
                errors.append(f'{tab} {rec["plate_name"]}({pid}): {e}')
    return tabs,errors


def fetch_kline(code):
    code = str(code).strip().zfill(6)

    # 上海市场：5、6、9开头，以及科创板指数000688
    # 深圳市场：1、2、3开头
    if code == '000688':
        secid = '1.000688'
    elif code.startswith(('5', '6', '9')):
        secid = '1.' + code
    elif code.startswith(('1', '2', '3')):
        secid = '0.' + code
    else:
        raise FetchError(f'{code}: 无法识别证券市场')

    url = 'https://push2his.eastmoney.com/api/qt/stock/kline/get'

    params = {
        'secid': secid,
        'klt': 101,
        'fqt': 1,
        'fields1': 'f1,f2,f3,f4,f5,f6',
        'fields2': 'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61',
        'beg': '0',
        'end': '20500101',
        'lmt': 60
    }

    # 不再访问东方财富网页预热Session
    obj = get_json(url, params)

    if not isinstance(obj, dict):
        raise FetchError(f'{code}: 接口返回格式异常')

    data = obj.get('data') or {}
    lines = data.get('klines')

    if not isinstance(lines, list) or len(lines) < 21:
        raise FetchError(f'{code}: K线不足21根或接口无数据')

    out = []

    for line in lines:
        f = line.split(',')

        if len(f) < 6:
            raise FetchError(f'{code}: K线字段不足')

        try:
            out.append({
                'date': f[0],
                'close': float(f[2]),
                'volume': float(f[5])
            })
        except (ValueError, TypeError, IndexError) as exc:
            raise FetchError(
                f'{code}: K线数据解析失败: {exc}'
            ) from exc

    return out


def ma(lines,n,offset=0):
    end=len(lines)-offset
    return sum(x['close'] for x in lines[end-n:end])/n

def collect_etfs(etfs,expected_date):
    result=[];errors=[]
    for item in etfs:
        code=item['code']
        try:
            lines=fetch_kline(code)
            if lines[-1]['date']!=expected_date: raise FetchError(f'最新K线日期{lines[-1]["date"]}非{expected_date}')
            if lines[-2]['volume']<=0: raise FetchError('前一日成交量为0，无法计算量比')
            now={str(n):ma(lines,n) for n in (5,10,20)}
            prev={str(n):ma(lines,n,1) for n in (5,10,20)}
            bull=lambda m:m['5']>m['10']>m['20']
            ratio=lines[-1]['volume']/lines[-2]['volume']
            signals=[]
            if bull(now) and not bull(prev):signals.append('新转多头排列')
            if ratio>=1.5:
                if now['5']>now['10']: signals.append('上升放量')
                elif now['5']<now['10']: signals.append('下降放量')
            result.append({**item,'close':lines[-1]['close'],'volume_ratio':ratio,'ma_today':now,'ma_previous':prev,'signals':signals})
        except (FetchError,KeyError,TypeError,ValueError,IndexError) as e:errors.append(f'{code} {item["name"]}: {e}')
    return result,errors
