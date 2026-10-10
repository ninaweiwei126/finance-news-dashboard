# NVDA + GOOGL 每日信号

这是一个无需电脑开机的手机 PWA 看板。GitHub Actions 会在美股收盘后自动拉取最新行情，并部署到 GitHub Pages。

## 第一次设置

1. 在 GitHub 新建一个 Public 仓库。
2. 把本目录中的所有文件上传到仓库根目录，确保 `.github` 目录也上传。
3. 打开仓库的 Settings -> Pages。
4. 将 Build and deployment -> Source 设置为 GitHub Actions。
5. 打开仓库的 Actions，选择 `Update NVDA GOOGL Signal`，点击 `Run workflow` 做第一次部署。
6. 部署完成后，Pages 页面会显示手机访问地址。

## 手机安装

1. 用手机 Safari 或 Chrome 打开 GitHub Pages 地址。
2. iPhone：分享 -> 添加到主屏幕。
3. Android：菜单 -> 安装应用或添加到主屏幕。

## 自动更新

工作流默认在每个美股交易日收盘后自动运行：

`15 22 * * 1-5`（UTC）

GitHub Pages 使用 HTTPS，因此不需要 Mac 开机，也不需要同一个 Wi-Fi。

## 说明

- 静态 PWA 可以自动更新页面内容，但不能单独发送后台推送通知。
- 如果需要“触发信号时主动通知”，下一步可以在这套 GitHub Actions 中加入邮件、Telegram 或企业微信机器人通知。
- 数据源为 Nasdaq 公共行情，可能包含延迟或收盘数据。

## 邮件推送

在 GitHub 仓库的 Settings -> Secrets and variables -> Actions 中添加：

- `MAIL_USERNAME`：发送邮件的 Gmail 地址；
- `MAIL_APP_PASSWORD`：Gmail 应用专用密码，不是 Google 登录密码；
- `MAIL_TO`：接收通知的邮箱。

邮件只在 NVDA 或 GOOGL 信号状态发生变化时发送。可在 Actions 中手动运行工作流，并勾选 `send_test_email` 做测试。
