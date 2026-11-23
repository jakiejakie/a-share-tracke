
def collect_etfs(etfs, expected_date):
    result = []
    errors = []

    for item in etfs:
        code = item['code']

        try:
            lines = fetch_kline(code)

            if len(lines) < 21:
                raise FetchError('有效K线不足21根')

            # 核对最新行情日期
            if lines[-1]['date'] != expected_date:
                raise FetchError(
                    f'最新K线日期{lines[-1]["date"]}非{expected_date}'
                )

            # 今日与前一交易日数据
            close_today = lines[-1]['close']
            close_previous = lines[-2]['close']

            volume_today = lines[-1]['volume']
            volume_previous = lines[-2]['volume']

            if volume_previous <= 0:
                raise FetchError('前一日成交量为0，无法计算量比')

            # 计算均线
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

            # 新转多头排列
            bull_today = ma5 > ma10 > ma20
            bull_previous = (
                prev['5'] > prev['10'] > prev['20']
            )

            # 成交量比
            ratio = volume_today / volume_previous

            signals = []

            # 信号A：新转多头排列
            if bull_today and not bull_previous:
                signals.append('新转多头排列')

            # 信号B：放量信号
            if ratio >= 1.5:

                # 先判断当天实际涨跌
                if close_today > close_previous:
                    direction = '上涨'
                elif close_today < close_previous:
                    direction = '下跌'
                else:
                    direction = '平盘'

                # 再判断短期均线趋势
                if ma5 > ma10:
                    trend = '多头'
                elif ma5 < ma10:
                    trend = '空头排列'
                else:
                    trend = '均线持平'

                # 组合成准确的信号名称
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
                    signals.append(f'放量平盘·{trend}')

            result.append({
                **item,
                'close': close_today,
                'previous_close': close_previous,
                'daily_change_pct': (
                    (close_today / close_previous - 1) * 100
                    if close_previous > 0 else None
                ),
                'volume_ratio': ratio,
                'ma_today': now,
                'ma_previous': prev,
                'signals': signals
            })

        except Exception as e:
            errors.append(
                f'{code} {item.get("name", "")}: '
                f'{type(e).__name__}: {e}'
            )

    return result, errors
