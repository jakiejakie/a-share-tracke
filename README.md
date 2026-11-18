# A股板块 + ETF 三日跟踪（邮件版）

## 功能
- 周一至周五北京时间15:45（UTC 07:45）尝试运行；由上证指数接口核对当日交易日期，休市日不生成数据。
- 选股通行业/概念/风格各前三板块、板块涨幅前10股票；每日完整板块JSON快照保存在 `snapshots/YYYY-MM-DD.json`。
- 以三个完整历史快照比较连续三日板块与股票。
- 固定34个标的，东财日K计算MA5/MA10/MA20与成交量比，输出Markdown报告到 `reports/YYYY-MM-DD.md`，通过SMTP发送邮件。
- 单个请求最多尝试3次（首次+2次重试）；接口无法访问时明确失败，不伪造数据。

## GitHub部署
1. 创建 **Private** 仓库 `a-share-tracker`，把压缩包内所有文件及隐藏目录 `.github` 上传至仓库根目录。
2. Settings → Secrets and variables → Actions → New repository secret，逐项设置：
   - `SMTP_HOST`：邮箱服务商提供的SMTP服务器，例如QQ邮箱 `smtp.qq.com`，163邮箱 `smtp.163.com`。
   - `SMTP_PORT`：一般为 `465`（SSL），也可使用 `587`（STARTTLS）。
   - `SMTP_USER`：发件邮箱地址。
   - `SMTP_PASSWORD`：邮箱SMTP授权码/应用密码，**不是GitHub密码**，通常也不是邮箱登录密码。
   - `MAIL_FROM`：发件邮箱地址（通常与SMTP_USER一致）。
   - `MAIL_TO`：收件邮箱地址。
3. Settings → Actions → General → Workflow permissions：选择 **Read and write permissions**（如可选）。同时确保仓库允许Actions推送。
4. Actions → A-share daily tracker → Run workflow，进行手动测试；查看日志、收到的邮件、`snapshots/`和`reports/`。
5. 查看运行日志的DNS/HTTP/反爬错误。GitHub云端IP可能被数据商拦截；若如此，需换成能访问接口的自托管runner或其他合规数据源。

## 注意事项
- GitHub Actions的定时触发可能延迟，不能保证15:45整点启动。
- 邮件发送成功与Git提交成功是两个独立步骤；如提交失败，Actions会标红，需要人工处理。
- 只有板块抓取完整才会保存正式历史快照。ETF单独失败会报告缺失，不影响板块历史快照。
- 该项目未经过目标数据接口的线上端到端验证，首次运行需确认API实际返回结构，可能需要调整解析器。
- 如果SMTP配置错误，报告可能已经写入工作区，但邮件发送失败；Actions仍尝试提交报告。
- 同一日期重复手动运行会覆盖该日期的快照/报告，不会新增第二份日期记录。
- 休市时仅在Actions日志显示“今日非交易日，跳过本次执行”，不发日报。
- 任务使用HTTP数据源，不构成投资建议。
