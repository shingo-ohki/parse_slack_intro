# parse_slack_intro
Slackに投稿された自己紹介メッセージをからコピペされたテキストファイル(post.txt) から構造化データとしてJSONに出力します。

## 使い方
- post.txt に Slack に投稿された自己紹介をコピペ
- python main_slack.py

解析されたデータはanalysis_results.jsonとして保存されます