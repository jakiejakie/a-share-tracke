import json
import os
import smtplib
import sys
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from zoneinfo import ZoneInfo
from src.collector import market_date,collect_plates,collect_etfs,FetchError
from src.report import compare,render

ROOT=Path(__file__).resolve().parent
TODAY=datetime.now(ZoneInfo('Asia/Shanghai')).date().isoformat()

def mail(subject,body):
    host=os.environ.get('SMTP_HOST'); user=os.environ.get('SMTP_USER');password=os.environ.get('SMTP_PASSWORD')
    sender=os.environ.get('MAIL_FROM') or user;to=os.environ.get('MAIL_TO')
    if not all((host,user,password,sender,to)):raise RuntimeError('缺少SMTP_HOST/SMTP_USER/SMTP_PASSWORD/MAIL_TO')
    msg=EmailMessage();msg['Subject']=subject;msg['From']=sender;msg['To']=to
    msg.set_content(body)
    port=int(os.environ.get('SMTP_PORT','465'))
    if port==465:
        with smtplib.SMTP_SSL(host,port,timeout=30) as s:s.login(user,password);s.send_message(msg)
    else:
        with smtplib.SMTP(host,port,timeout=30) as s:
            s.starttls();s.login(user,password);s.send_message(msg)

def main():
    try:
        latest=market_date().isoformat()
    except Exception as e:
        msg=f'交易日判断接口失败，无法确认是否交易日：{e}。未生成快照，未抓取ETF。'
        print(msg);mail(f'【A股监控异常】{TODAY}',msg);return 1
    if latest!=TODAY:
        print('今日非交易日，跳过本次执行');return 0
    errors=[]
    try:tabs,plate_errors=collect_plates();errors.extend(plate_errors)
    except Exception as e:
        tabs={'行业板块':[],'概念板块':[],'风格板块':[]};errors.append(f'板块排名或元数据失败：{e}')
    etf_config=json.loads((ROOT/'config/etfs.json').read_text(encoding='utf-8'))
    etfs,etf_errors=collect_etfs(etf_config,TODAY);errors.extend(etf_errors)
    snapshot={'date':TODAY,'tabs':tabs}
    complete=not plate_errors if 'plate_errors' in locals() else False
    complete=complete and all(len(tabs[t])==3 for t in tabs)
    if complete:
        folder=ROOT/'snapshots';folder.mkdir(exist_ok=True)
        path=folder/f'{TODAY}.json'
        path.write_text(json.dumps(snapshot,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        days,hits,stocks=compare(snapshot,folder)
    else:
        days=[snapshot];hits=[];stocks=[]
        errors.append('板块快照不完整：未写入正式历史快照，不能进行可靠三日判断')
    report=render(snapshot,etfs,errors,days,hits,stocks)
    out=ROOT/'reports';out.mkdir(exist_ok=True)
    (out/f'{TODAY}.md').write_text(report,encoding='utf-8')
    print(report)
    mail(f'【A股板块+ETF日报】{TODAY}'+('（部分数据异常）' if errors else ''),report)
    return 0 if not errors else 2

if __name__=='__main__':
    try:sys.exit(main())
    except Exception as e:
        print(f'任务失败：{type(e).__name__}: {e}',file=sys.stderr)
        sys.exit(1)
