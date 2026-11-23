
from pathlib import Path
import json


# =========================
# 三日历史比较
# =========================

def compare(today, folder):
    paths = sorted(
        x for x in Path(folder).glob('????-??-??.json')
        if x.stem < today['date']
    )

    history = []

    for path in reversed(paths):
        try:
            data = json.loads(
                path.read_text(encoding='utf-8')
            )

            valid = (
                data.get('date') == path.stem
                and all(
                    len(data['tabs'][tab]) == 3
                    for tab in (
                        '行业板块',
                        '概念板块',
                        '风格板块'
                    )
                )
            )

            if valid:
                history.append(data)

            if len(history) == 2:
                break

        except (
            ValueError,
            KeyError,
            TypeError
        ):
            continue

    days = list(reversed(history)) + [today]

    if len(days) < 3:
        return days, [], []

    # 板块：同一tab、同一板块名称
    plates = []

    for tab in today['tabs']:
        sets = [
            {
                p['plate_name']: p
                for p in day['tabs'][tab]
            }
            for day in days
        ]

        common_names = set.intersection(
            *(set(x.keys()) for x in sets)
        )

        for name in common_names:
            plates.append({
                'tab': tab,
                'name': name,
                'changes': [
                    (
                        day['date'],
                        data[name]['core_avg_pcp']
                    )
                    for day, data in zip(days, sets)
                ]
            })

    # 股票：跨任意tab匹配股票代码
    daily = []

    for day in days:
        bycode = {}

        for tab, items in day['tabs'].items():
            for plate in items:
                for stock in plate['top10_stocks']:
                    symbol = stock['symbol']

                    bycode.setdefault(
                        symbol,
                        {
                            'name': stock['name'],
                            'plates': set()
                        }
                    )['plates'].add(
                        f'{tab}/{plate["plate_name"]}'
                    )

        daily.append(bycode)

    stocks = []

    common_symbols = set.intersection(
        *(set(x.keys()) for x in daily)
    )

    for symbol in common_symbols:
        stocks.append({
            'symbol': symbol,
            'name': daily[-1][symbol]['name'],
            'days': [
                (
                    day['date'],
                    sorted(data[symbol]['plates'])
                )
                for day, data in zip(days, daily)
            ]
        })

    return (
        days,
        sorted(
            plates,
            key=lambda x: (x['tab'], x['name'])
        ),
        sorted(
            stocks,
            key=lambda x: x['symbol']
        )
    )


# =========================
# 日报生成
# =========================

def render(snapshot, etfs, errors, days, plate_hits, stock_hits):

    date = snapshot['date']
    out = []

    def add_table(headers, rows):
        def cell(value):
            return (
                str(value)
                .replace('|', '\\|')
                .replace('\n', ' ')
            )

        out.append(
            '| ' + ' | '.join(
                cell(x) for x in headers
            ) + ' |'
        )

        out.append(
            '| ' + ' | '.join(
                ['---'] * len(headers)
            ) + ' |'
        )

        for row in rows:
            out.append(
                '| ' + ' | '.join(
                    cell(x) for x in row
                ) + ' |'
            )

        out.append('')

    def fmt_pct(value):
        return f'{float(value) * 100:+.2f}%'

    def fmt_num(value):
        return f'{float(value):.3f}'

    def fmt_change(value):
        if value is None:
            return '数据缺失'
        return f'{float(value):+.2f}%'

    # 所有ETF信号分类
    categories = (
        '新转多头排列',
        '放量上涨·多头',
        '放量反弹·空头排列',
        '放量上涨·均线持平',
        '放量回调·多头排列',
        '放量下跌·空头',
        '放量下跌·均线持平',
        '放量平盘·多头',
        '放量平盘·空头排列',
        '放量平盘·均线持平'
    )

    matched = {
        category: [
            x for x in etfs
            if category in x.get('signals', [])
        ]
        for category in categories
    }

    # ETF表格行
    def etf_rows(items, include_previous=False):
        rows = []

        for x in items:
            m = x['ma_today']

            row = [
                x['code'],
                x['name'],
                fmt_change(x.get('daily_change_pct')),
                fmt_num(x['close']),
                f'{x["volume_ratio"]:.2f}',
                fmt_num(m['5']),
                fmt_num(m['10'])
            ]

            if include_previous:
                p = x['ma_previous']

                row += [
                    fmt_num(m['20']),
                    fmt_num(p['5']),
                    fmt_num(p['10']),
                    fmt_num(p['20'])
                ]

            rows.append(row)

        return rows

    # =========================
    # 一、今日结论
    # =========================

    out += [
        f'# A股监控日报 | {date}',
        '',
        '## 一、今日结论',
        ''
    ]

    enough_history = len(days) >= 3

    summary = [
        [
            '连续三日板块',
            len(plate_hits) if enough_history else '待累计',
            '有信号' if plate_hits else (
                '无信号' if enough_history
                else f'历史不足，仅{len(days)}天'
            )
        ],
        [
            '连续三日股票',
            len(stock_hits) if enough_history else '待累计',
            '有信号' if stock_hits else (
                '无信号' if enough_history
                else f'历史不足，仅{len(days)}天'
            )
        ]
    ]

    for category in categories:
        count = len(matched[category])

        summary.append([
            f'ETF {category}',
            count,
            '有信号' if count else '无信号'
        ])

    summary.append([
        'ETF数据异常',
        len([
            e for e in errors
            if any(
                str(x['code']) in e
                for x in etfs
            )
        ]),
        '请检查异常明细'
    ])

    add_table(
        ['监控项目', '数量', '结论'],
        summary
    )

    if errors:
        out += [
            f'**数据提醒：共有{len(errors)}项异常，'
            '未获取的数据不参与信号计算。**',
            ''
        ]

    # =========================
    # 二、连续三日板块
    # =========================

    out += [
        '## 二、连续三日板块',
        ''
    ]

    if not enough_history:
        out += [
            f'历史数据不足，仅累计{len(days)}天。',
            ''
        ]

    elif not plate_hits:
        out += [
            '今日无连续三天出现的板块。',
            ''
        ]

    else:
        rows = []

        for p in plate_hits:
            rows.append([
                p['tab'],
                p['name'],
                *[
                    fmt_pct(value)
                    for _, value in p['changes']
                ]
            ])

        add_table(
            [
                '分类',
                '板块',
                *[day['date'] for day in days]
            ],
            rows
        )

    # =========================
    # 三、连续三日股票
    # =========================

    out += [
        '## 三、连续三日股票',
        ''
    ]

    if not enough_history:
        out += [
            f'历史数据不足，仅累计{len(days)}天。',
            ''
        ]

    elif not stock_hits:
        out += [
            '今日无连续三天出现的股票。',
            ''
        ]

    else:
        rows = []

        for stock in stock_hits:
            row = [
                stock['symbol'],
                stock['name']
            ]

            for _, plates in stock['days']:
                row.append('、'.join(plates))

            rows.append(row)

        add_table(
            [
                '代码',
                '股票',
                *[
                    day['date'] + '所属板块'
                    for day in days
                ]
            ],
            rows
        )

    # =========================
    # 四、ETF交易信号
    # =========================

    out += [
        '## 四、ETF交易信号',
        ''
    ]

    for category in categories:
        items = matched[category]

        out += [
            f'### {category}（{len(items)}只）',
            ''
        ]

        if not items:
            out += ['无。', '']
            continue

        if category == '新转多头排列':
            add_table(
                [
                    '代码',
                    'ETF',
                    '当日涨跌',
                    '收盘',
                    '量比',
                    'MA5',
                    'MA10',
                    'MA20',
                    '前MA5',
                    '前MA10',
                    '前MA20'
                ],
                etf_rows(items, include_previous=True)
            )

        else:
            add_table(
                [
                    '代码',
                    'ETF',
                    '当日涨跌',
                    '收盘',
                    '量比',
                    'MA5',
                    'MA10'
                ],
                etf_rows(items)
            )

    # =========================
    # 五、完整板块数据
    # =========================

    out += [
        '## 五、板块完整数据',
        '',
        '以下为三个分类各前三板块及其涨幅前十股票。',
        ''
    ]

    for tab, items in snapshot['tabs'].items():
        out += [
            f'### {tab}',
            ''
        ]

        plate_rows = []

        for rank, plate in enumerate(items, 1):
            plate_rows.append([
                rank,
                plate['plate_name'],
                fmt_pct(plate['core_avg_pcp']),
                plate['constituent_count'],
                plate['skipped_no_data']
            ])

        if plate_rows:
            add_table(
                ['排名', '板块', '涨幅', '成分股', '跳过'],
                plate_rows
            )
        else:
            out += [
                '无有效板块数据。',
                ''
            ]

        for rank, plate in enumerate(items, 1):
            out += [
                f'**{rank}. {plate["plate_name"]}：'
                f'涨幅{fmt_pct(plate["core_avg_pcp"])}**',
                ''
            ]

            stock_rows = [
                [
                    index,
                    stock['symbol'],
                    stock['name'],
                    fmt_pct(stock['change_percent'])
                ]
                for index, stock in enumerate(
                    plate['top10_stocks'], 1
                )
            ]

            if stock_rows:
                add_table(
                    ['排名', '代码', '股票', '涨幅'],
                    stock_rows
                )
            else:
                out += [
                    '无有效股票数据。',
                    ''
                ]

    # =========================
    # 六、未触发ETF
    # =========================

    inactive = [
        x for x in etfs
        if not x.get('signals')
    ]

    out += [
        f'## 六、未触发ETF（{len(inactive)}只）',
        ''
    ]

    if inactive:
        add_table(
            ['代码', 'ETF', '当日涨跌', '收盘价', '量比'],
            [
                [
                    x['code'],
                    x['name'],
                    fmt_change(x.get('daily_change_pct')),
                    fmt_num(x['close']),
                    f'{x["volume_ratio"]:.2f}'
                ]
                for x in inactive
            ]
        )

    else:
        out += ['无。', '']

    # =========================
    # 七、数据异常
    # =========================

    if errors:
        out += [
            '## 七、数据异常',
            ''
        ]

        add_table(
            ['序号', '异常说明'],
            [
                [index, error]
                for index, error in enumerate(errors, 1)
            ]
        )

        out += [
            '**注意：数据缺失的标的未参与信号计算，'
            '不能将数据缺失解释为没有信号。**',
            ''
        ]

    return '\n'.join(out)
