
import time
import random
import traceback
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.parse import urlparse

import requests


TZ = ZoneInfo('Asia/Shanghai')

SESSION = requests.Session()
SESSION.headers.update({
    'User-Agent': (
        'Mozilla/5.0 (X11; Linux x86_64) '
        'AppleWebKit/537.36 Chrome/131.0 Safari/537.36'
    ),
    'Accept': 'application/json,text/plain,*/*',
    'Referer': 'https://xuangutong.com.cn/'
})


class FetchError(Exception):
    pass


# =========================
# 通用请求
# =========================

def get_json(url, params=None):
    last = None

    for attempt in range(3):
        try:
            with requests.Session() as session:
                session.headers.update({
                    'User-Agent': (
                        'Mozilla/5.0 (X11; Linux x86_64) '
                        'AppleWebKit/537.36 Chrome/131.0 Safari/537.36'
                    ),
                    'Accept': 'application/json,text/plain,*/*',
                    'Connection': 'close'
                })

                response = session.get(
                    url,
                    params=params,
                    timeout=(8, 18)
                )

                response.raise_for_status()
                obj = response.json()

                if not isinstance(obj, dict):
                    raise ValueError('返回内容不是JSON对象')

                return obj

        except (requests.RequestException, ValueError) as exc:
            last = exc

            if attempt < 2:
                time.sleep(
                    2 ** (attempt + 1) + random.uniform(0, 2)
                )

    raise FetchError(
        f'{urlparse(url).netloc}: '
        f'3次请求均失败，最后错误：{last}'
    )


# =========================
# 交易日判断
# =========================

def market_date():
    obj = get_json(
        'https://api-ddc-wscn.xuangubao.com.cn/market/trend',
        {
            'fields': 'tick_at,close_px',
            'prod_code': '000001.SS'
        }
    )

    try:
        lines = obj['data']['candle']['000001.SS']['lines']
    except (KeyError, TypeError) as exc:
        raise FetchError('上证指数交易日数据结构异常') from exc

    if not isinstance(lines, list) or not lines:
        raise FetchError('上证指数交易日数据为空')

    last = lines[-1]

    if not isinstance(last, (list, tuple)) or len(last) < 2:
        raise FetchError('上证指数最后一条记录格式异常')

    return datetime.fromtimestamp(
        float(last[0]), TZ
    ).date()


# =========================
# 板块数据
# =========================

def rank_ids(typ):
    obj = get_json(
        'https://flash-api.xuangubao.com.cn/api/plate/rank',
        {
            'field': 'core_avg_pcp',
            'type': typ
        }
    )

    data = obj.get('data')

    if not isinstance(data, list) or len(data) < 3:
        raise FetchError(
            f'板块rank type={typ}返回不足3个ID或结构异常'
        )

    return [str(v) for v in data[:3]]


def plate_meta(ids):
    obj = get_json(
        'https://flash-api.xuangubao.com.cn/api/plate/data',
        {
            'fields': 'plate_id,plate_name,core_avg_pcp',
            'plates': ','.join(ids)
        }
    )

    data = obj.get('data')

    if isinstance(data, list):
        records = data
    elif isinstance(data, dict):
        records = list(data.values())
    else:
        raise FetchError('plate/data结构异常')

    result = {}

    for rec in records:
        if not isinstance(rec, dict):
            continue

        pid = str(rec.get('plate_id', ''))

        if pid in ids:
            result[pid] = rec

    return result


def stock_symbols(pid):
    obj = get_json(
        'https://flash-api.xuangubao.com.cn/api/plate/plate_set',
        {
            'id': pid,
            'display_premium_stock': 'true'
        }
    )

    try:
        stocks = obj['data']['stocks']
    except (KeyError, TypeError) as exc:
        raise FetchError(
            f'板块{pid}股票列表结构异常'
        ) from exc

    if not isinstance(stocks, list):
        raise FetchError(f'板块{pid} stocks结构异常')

    symbols = []

    for item in stocks:
        symbol = (
            item.get('symbol')
            if isinstance(item, dict)
            else item
        )

        if symbol:
            symbols.append(str(symbol))

    return list(dict.fromkeys(symbols))


def stock_quotes(symbols):
    all_rows = []

    for start in range(0, len(symbols), 50):
        batch = symbols[start:start + 50]

        obj = get_json(
            'https://flash-api.xuangubao.com.cn/api/stock/data',
            {
                'symbols': ','.join(batch),
                'fields': (
                    'symbol,stock_chi_name,'
                    'change_percent,price'
                ),
                'strict': 'true'
            }
        )

        data = obj.get('data')

        if isinstance(data, list):
            rows = data
        elif isinstance(data, dict):
            rows = list(data.values())
        else:
            raise FetchError('stock/data结构异常')

        all_rows.extend(
            row for row in rows
            if isinstance(row, dict)
        )

    return all_rows


def collect_plates():
    tabs_ids = {
        '行业板块': rank_ids(2),
        '概念板块': rank_ids(1),
        '风格板块': rank_ids(3)
    }

    ids = list(dict.fromkeys(
        sum(tabs_ids.values(), [])
    ))

    meta = plate_meta(ids)

    tabs = {}
    errors = []

    for tab, tab_ids in tabs_ids.items():
        tabs[tab] = []

        for pid in tab_ids:
            rec = meta.get(pid)

            if (
                not rec
                or not rec.get('plate_name')
                or rec.get('core_avg_pcp') is None
            ):
                errors.append(
                    f'{tab} {pid}: plate/data缺少名称或涨幅'
                )
                continue

            try:
                symbols = stock_symbols(pid)
                rows = stock_quotes(symbols)

                wanted = set(symbols)
                valid = {}

                for row in rows:
                    try:
                        sym = str(row['symbol'])
                        pct = float(row['change_percent'])
                        price = float(row['price'])
                        name = row.get('stock_chi_name')

                        if (
                            sym in wanted
                            and name
                            and price > 0
                        ):
                            valid[sym] = {
                                'name': str(name),
                                'symbol': sym,
                                'change_percent': pct
                            }

                    except (ValueError, TypeError, KeyError):
                        continue

                top = sorted(
                    valid.values(),
                    key=lambda x: x['change_percent'],
                    reverse=True
                )[:10]

                tabs[tab].append({
                    'plate_id': pid,
                    'plate_name': str(rec['plate_name']),
                    'core_avg_pcp': float(rec['core_avg_pcp']),
                    'top10_stocks': top,
                    'constituent_count': len(symbols),
                    'skipped_no_data': len(symbols) - len(valid)
                })

            except (
                FetchError,
                KeyError,
                TypeError,
                ValueError
            ) as exc:
                errors.append(
                    f'{tab} {rec["plate_name"]}({pid}): {exc}'
                )

    return tabs, errors


# =========================
# ETF日K数据
# =========================

def fetch_kline(code):
    code = str(code).strip().zfill(6)

    if code == '000688':
        symbol = 'sh000688'
    elif code.startswith(('5', '6', '9')):
        symbol = 'sh' + code
    elif code.startswith(('1', '2', '3')):
        symbol = 'sz' + code
    else:
        raise FetchError(
            f'{code}: 无法识别证券市场'
        )

    url = 'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get'

    params = {
        'param': f'{symbol},day,,,80,qfq'
    }

    try:
        obj = get_json(url, params)

        data = (
            (obj.get('data') or {}).get(symbol) or {}
        )

        lines = data.get('qfqday') or data.get('day')

        if not isinstance(lines, list) or len(lines) < 21:
            raise FetchError(
                f'{code}: 腾讯K线不足21根或无数据'
            )

        out = []

        for row in lines:
            if not isinstance(row, list) or len(row) < 6:
                raise FetchError(
                    f'{code}: K线字段异常'
                )

            out.append({
                'date': str(row[0]),
                'close': float(row[2]),
                'volume': float(row[5])
            })

        out.sort(key=lambda x: x['date'])

        dates = [x['date'] for x in out]

        if len(dates) != len(set(dates)):
            raise FetchError(
                f'{code}: 存在重复K线日期'
            )

        if any(
            x['close'] <= 0 or x['volume'] < 0
            for x in out
        ):
            raise FetchError(
                f'{code}: K线价格或成交量异常'
            )

        return out

    except FetchError:
        raise

    except (
        requests.RequestException,
        ValueError,
        TypeError,
        KeyError
    ) as exc:
        raise FetchError(
            f'{code}: 腾讯行情获取失败: {exc}'
        ) from exc


# =========================
# 均线计算
# =========================

def ma(lines, n, offset=0):
    end = len(lines) - offset

    if end < n:
        raise FetchError(
            f'计算MA{n}时有效K线不足'
        )

    values = [
        float(x['close'])
        for x in lines[end - n:end]
    ]

    return sum(values) / n


# =========================
# ETF信号计算
# =========================

def collect_etfs(etfs, expected_date):
    result = []
    errors = []

    for item in etfs:
        code = str(item['code'])

        try:
            lines = fetch_kline(code)

            if len(lines) < 21:
                raise FetchError('有效K线不足21根')

            if lines[-1]['date'] != expected_date:
                raise FetchError(
                    f'最新K线日期{lines[-1]["date"]}'
                    f'非{expected_date}'
                )

            close_today = lines[-1]['close']
            close_previous = lines[-2]['close']

            volume_today = lines[-1]['volume']
            volume_previous = lines[-2]['volume']

            if close_previous <= 0:
                raise FetchError('前一日收盘价无效')

            if volume_previous <= 0:
                raise FetchError('前一日成交量为0，无法计算量比')

            now = {
                str(n): ma(lines, n)
                for n in (5, 10, 20)
            }

            prev = {
                str(n): ma(lines, n, 1)
                for n in (5, 10, 20)
            }

            ma5 = now['5']
            ma10 = now['10']
            ma20 = now['20']

            bull_today = ma5 > ma10 > ma20
            bull_previous = (
                prev['5'] > prev['10'] > prev['20']
            )

            ratio = volume_today / volume_previous

            daily_change_pct = (
                close_today / close_previous - 1
            ) * 100

            signals = []

            # 信号A：新转多头排列
            if bull_today and not bull_previous:
                signals.append('新转多头排列')

            # 信号B：放量，要求量比至少1.5倍
            if ratio >= 1.5:

                if close_today > close_previous:
                    direction = '上涨'
                elif close_today < close_previous:
                    direction = '下跌'
                else:
                    direction = '平盘'

                if ma5 > ma10:
                    trend = '多头'
                elif ma5 < ma10:
                    trend = '空头排列'
                else:
                    trend = '均线持平'

                if direction == '上涨':
                    if trend == '多头':
                        signals.append('放量上涨·多头')
                    elif trend == '空头排列':
                        signals.append('放量反弹·空头排列')
                    else:
                        signals.append('放量上涨·均线持平')

                elif direction == '下跌':
                    if trend == '多头':
                        signals.append('放量回调·多头排列')
                    elif trend == '空头排列':
                        signals.append('放量下跌·空头')
                    else:
                        signals.append('放量下跌·均线持平')

                else:
                    signals.append(
                        f'放量平盘·{trend}'
                    )

            result.append({
                **item,
                'close': close_today,
                'previous_close': close_previous,
                'daily_change_pct': daily_change_pct,
                'volume_ratio': ratio,
                'ma_today': now,
                'ma_previous': prev,
                'signals': signals
            })

        except Exception as exc:
            errors.append(
                f'{code} {item.get("name", "")}: '
                f'{type(exc).__name__}: {exc}\n'
                f'{traceback.format_exc()}'
            )

    return result, errors
