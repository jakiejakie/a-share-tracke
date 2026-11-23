from pathlib import Path
import json
import markdown

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


def render(snapshot, etfs, errors, days, plate_hits, stock_hits):
    date = snapshot['date']
    out = []

    def add_table(headers, rows):
        """生成Markdown表格"""
        def cell(value):
            return str(value).replace('|', '\\|').replace('\n', ' ')

        out.append('| ' + ' | '.join(map(cell, headers)) + ' |')
        out.append('| ' + ' | '.join(['---'] * len(headers)) + ' |')

        for row in rows:
            out.append('| ' + ' | '.join(map(cell, row)) + ' |')

        out.append('')

    def fmt_pct(value):
        return f'{float(value) * 100:+.2f}%'

    def fmt_num(value):
        return f'{float(value):.3f}'

    def etf_rows(items, include_previous=False):
        rows = []
        for x in items:
            m = x['ma_today']
            row = [
                x['code'],
                x['name'],
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
        c: [x for x in etfs if c in x['signals']]
        for c in categories
    }

    # =========================
    # 一、结论汇总
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
                '无信号' if enough_history else
                f'历史不足，仅{len(days)}天'
            )
        ],
        [
            '连续三日股票',
            len(stock_hits) if enough_history else '待累计',
            '有信号' if stock_hits else (
                '无信号' if enough_history else
                f'历史不足，仅{len(days)}天'
            )
        ]
    ]

    for c in categories:
        count = len(matched[c])
        summary.append([
            f'ETF{c}',
            count,
            '有信号' if count else '无信号'
        ])

    add_table(['监控项目', '数量', '结论'], summary)

    if errors:
        out += [
            f'**数据提醒：存在{len(errors)}项异常，'
            '上述结果仅基于成功获取的数据，'
            '不能视为完整市场结论。**',
            ''
        ]

    # =========================
    # 二、连续三日板块
    # =========================
    out += ['## 二、连续三日板块', '']

    if not enough_history:
        out += [
            f'历史数据不足，仅累计{len(days)}天。',
            ''
        ]
    elif not plate_hits:
        out += ['无符合条件的板块。', '']
    else:
        rows = []
        for p in plate_hits:
            changes = p['changes']
            rows.append([
                p['tab'],
                p['name'],
                fmt_pct(changes[0][1]),
                fmt_pct(changes[1][1]),
                fmt_pct(changes[2][1])
            ])

        add_table(
            [
                '分类',
                '板块',
                days[0]['date'],
                days[1]['date'],
                days[2]['date']
            ],
            rows
        )

    # =========================
    # 三、连续三日股票
    # =========================
    out += ['## 三、连续三日股票', '']

    if not enough_history:
        out += [
            f'历史数据不足，仅累计{len(days)}天。',
            ''
        ]
    elif not stock_hits:
        out += ['无符合条件的股票。', '']
    else:
        rows = []

        for s in stock_hits:
            row = [s['symbol'], s['name']]
            for day, plates in s['days']:
                row.append('、'.join(plates))
            rows.append(row)

        add_table(
            [
                '代码',
                '股票',
                days[0]['date'] + '所属板块',
                days[1]['date'] + '所属板块',
                days[2]['date'] + '所属板块'
            ],
            rows
        )

    # =========================
    # 四、ETF信号
    # =========================
    out += ['## 四、ETF交易信号', '']

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
                    '代码', 'ETF', '收盘',
                    '量比', 'MA5', 'MA10',
                    'MA20', '前MA5',
                    '前MA10', '前MA20'
                ],
                etf_rows(items, include_previous=True)
            )
        else:
            add_table(
                [
                    '代码', 'ETF', '收盘',
                    '量比', 'MA5', 'MA10'
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
        out += [f'### {tab}', '']

        plate_rows = []

        for rank, p in enumerate(items, 1):
            plate_rows.append([
                rank,
                p['plate_name'],
                fmt_pct(p['core_avg_pcp']),
                p['constituent_count'],
                p['skipped_no_data']
            ])

        if plate_rows:
            add_table(
                ['排名', '板块', '涨幅', '成分股', '跳过'],
                plate_rows
            )
        else:
            out += ['无有效板块数据。', '']

        for rank, p in enumerate(items, 1):
            out += [
                f'**{rank}. {p["plate_name"]}：涨幅'
                f'{fmt_pct(p["core_avg_pcp"])}**',
                ''
            ]

            stock_rows = [
                [
                    i,
                    s['symbol'],
                    s['name'],
                    fmt_pct(s['change_percent'])
                ]
                for i, s in enumerate(p['top10_stocks'], 1)
            ]

            if stock_rows:
                add_table(
                    ['排名', '代码', '股票', '涨幅'],
                    stock_rows
                )
            else:
                out += ['无有效股票数据。', '']

    # =========================
    # 六、未触发ETF
    # =========================
    inactive = [x for x in etfs if not x['signals']]

    out += [
        f'## 六、未触发ETF（{len(inactive)}只）',
        ''
    ]

    if inactive:
        add_table(
            ['代码', 'ETF', '收盘价', '量比'],
            [
                [
                    x['code'],
                    x['name'],
                    fmt_num(x['close']),
                    f'{x["volume_ratio"]:.2f}'
                ]
                for x in inactive
            ]
        )
    else:
        out += ['无。', '']

    # =========================
    # 七、异常信息
    # =========================
    if errors:
        out += [
            '## 七、数据异常',
            ''
        ]

        add_table(
            ['序号', '异常说明'],
            [
                [i, e]
                for i, e in enumerate(errors, 1)
            ]
        )

        out += [
            '**注意：异常标的未参与相关信号计算；'
            '数据缺失时不得将未检出信号解释为市场无信号。**',
            ''
        ]

    return '\n'.join(out)
