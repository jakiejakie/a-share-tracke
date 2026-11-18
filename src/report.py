from pathlib import Path
import json

def compare(today, folder):
    paths=sorted(x for x in Path(folder).glob('????-??-??.json') if x.stem<today['date'])
    history=[]
    for path in reversed(paths):
        try:
            x=json.loads(path.read_text(encoding='utf-8'))
            if x.get('date')==path.stem and all(len(x['tabs'][t])==3 for t in ('行业板块','概念板块','风格板块')):
                history.append(x)
            if len(history)==2:break
        except (ValueError,KeyError,TypeError):pass
    days=list(reversed(history))+[today]
    if len(days)<3:return days,[],[]
    plates=[];stocks=[]
    for tab in today['tabs']:
        sets=[{p['plate_name']:p for p in d['tabs'][tab]} for d in days]
        for name in set.intersection(*(set(s) for s in sets)):
            plates.append({'tab':tab,'name':name,'changes':[(d['date'],s[name]['core_avg_pcp']) for d,s in zip(days,sets)]})
    daily=[]
    for day in days:
        bycode={}
        for tab,items in day['tabs'].items():
            for plate in items:
                for stock in plate['top10_stocks']:
                    bycode.setdefault(stock['symbol'],{'name':stock['name'],'plates':set()})['plates'].add(f'{tab}/{plate["plate_name"]}')
        daily.append(bycode)
    for sym in set.intersection(*(set(x) for x in daily)):
        stocks.append({'symbol':sym,'name':daily[-1][sym]['name'],'days':[(d['date'],sorted(s[sym]['plates'])) for d,s in zip(days,daily)]})
    return days,sorted(plates,key=lambda x:(x['tab'],x['name'])),sorted(stocks,key=lambda x:x['symbol'])

def render(snapshot,etfs,errors,days,plate_hits,stock_hits):
    date=snapshot['date'];out=[f'# A股板块 + ETF 日报 | {date}','', '## 【板块部分】','']
    for tab,items in snapshot['tabs'].items():
        out += [f'### {tab}','']
        for i,p in enumerate(items,1):
            out += [f'**{i}. {p["plate_name"]}（{p["core_avg_pcp"]*100:+.2f}%）**  成分股{p["constituent_count"]}只；无行情/停牌/无有效报价跳过{p["skipped_no_data"]}只','']
            for j,s in enumerate(p['top10_stocks'],1):out.append(f'{j}. {s["name"]} `{s["symbol"]}` {s["change_percent"]*100:+.2f}%')
            out.append('')
    out += ['### 连续三日出现','']
    if len(days)<3:out += [f'**历史数据不足，仅累计{len(days)}天**（仅统计可读取的完整交易日快照）','']
    elif not plate_hits and not stock_hits:out += ['今日无连续三天出现的板块/股票','']
    else:
        out += ['**板块：**','']
        for p in plate_hits:out.append(f'- {p["tab"]} / {p["name"]}：'+ '；'.join(f'{d} {v*100:+.2f}%' for d,v in p['changes']))
        out += ['','**股票：**','']
        for s in stock_hits:out.append(f'- {s["name"]} `{s["symbol"]}`：'+'；'.join(f'{d} {", ".join(ps)}' for d,ps in s['days']))
        out.append('')
    out += ['## 【ETF部分】','']
    for category in ('新转多头排列','上升放量','下降放量'):
        out += [f'### {category}','']
        matching=[x for x in etfs if category in x['signals']]
        if not matching:out += ['无',''];continue
        for x in matching:
            m=x['ma_today'];pr=x['ma_previous']
            line=f'- {x["name"]} `{x["code"]}`：收盘 {x["close"]:.3f}，量比 {x["volume_ratio"]:.2f}倍；MA5 {m["5"]:.3f}，MA10 {m["10"]:.3f}'
            if category=='新转多头排列':line+=f'，MA20 {m["20"]:.3f}；前日MA5 {pr["5"]:.3f}，MA10 {pr["10"]:.3f}，MA20 {pr["20"]:.3f}'
            out.append(line)
        out.append('')
    out += ['### 未触发信号','']
    for x in etfs:
        if not x['signals']:out.append(f'- {x["name"]} `{x["code"]}`：收盘 {x["close"]:.3f}，量比 {x["volume_ratio"]:.2f}倍')
    out += ['','## 异常及数据完整性','']
    if errors:
        for e in errors:out.append(f'- {e}')
        out += ['','**影响：上述缺失项目无法参与完整统计；板块数据不完整时不能得出可靠的连续三日结论。**']
    else:out.append('无接口或数据校验异常。')
    out.append('')
    return '\n'.join(out)
