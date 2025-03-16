import requests
import json
import os
import re

# OLLAMA の設定
OLLAMA_CONFIG = {
    'base_url': 'http://ollama:11434/v1',
    'default_temperature': 0.0,
    'timeout': 60,
    'max_retries': 3,
    'api_key': 'ollama'
}

def get_local_llm(model, temperature=None):
    """
    ローカルLLMのインスタンスを取得するためのヘルパー関数。
    """
    model_name = model.split("local:")[1]
    return {
        "model": model_name,
        "temperature": temperature or OLLAMA_CONFIG['default_temperature'],
        "base_url": OLLAMA_CONFIG['base_url']
    }

def query_ollama(model, prompt):
    """
    OLLAMA サーバーに問い合わせを行い、結果を取得する関数。
    """
    url = f"{OLLAMA_CONFIG['base_url']}/chat/completions"
    payload = {
        "model": model["model"],
        "messages": [
            {"role": "system", "content": "あなたはテキスト解析の専門家です。指示された形式のJSONのみを出力してください。"},
            {"role": "user", "content": prompt}
        ],
        "temperature": model["temperature"]
    }
    
    response = requests.post(url, json=payload, timeout=OLLAMA_CONFIG['timeout'])
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]

def extract_posts_from_slack(file_path):
    """
    Slackのコピペから個別の投稿を抽出する関数
    """
    with open(file_path, "r", encoding="utf-8") as file:
        content = file.read()
    
    # タイムスタンプと名前のパターンでテキストを分割
    # 例: "ユーザー名\n  12:34" のようなパターン
    parts = re.split(r'(\n\s*\d{1,2}:\d{2}|\n\s*New\s*\n)', content)
    
    # 投稿のまとまりを検出
    posts = []
    current_post = ""
    
    for part in parts:
        if re.match(r'\n\s*\d{1,2}:\d{2}|\n\s*New\s*\n', part):
            # タイムスタンプを見つけたら、それまでの投稿を保存し新しい投稿を開始
            if current_post.strip():
                posts.append(current_post.strip())
            current_post = ""
        else:
            current_post += part
    
    # 最後の投稿を追加
    if current_post.strip():
        posts.append(current_post.strip())
    
    # 自己紹介っぽい投稿だけをフィルタリング
    valid_posts = []
    for post in posts:
        # 名前、興味、得意なことのキーワードが含まれているか確認
        if (("名前" in post or "：" in post) and 
            (re.search(r'[１1２2]\.', post) or "興味" in post or "プロジェクト" in post) and
            (re.search(r'[３3]\.', post) or "得意" in post)):
            
            # メッセージ参加通知を除外
            if not "#1_自己紹介 に参加しました" in post:
                valid_posts.append(clean_slack_post(post))
    
    print(f"合計 {len(valid_posts)} 件の有効な自己紹介投稿を見つけました。\n")
    return valid_posts

def clean_slack_post(post):
    """
    Slackの投稿から余分なフォーマットを削除
    """
    # リアクション（絵文字とカウント）を削除
    post = re.sub(r':[^:]+:\s*\d*', '', post)
    
    # URLの展開プレビューを削除
    lines = post.split('\n')
    cleaned_lines = []
    skip_next = 0
    
    for i, line in enumerate(lines):
        if skip_next > 0:
            skip_next -= 1
            continue
            
        # URL展開プレビューの開始行を検出
        if line.strip().startswith(('http', 'https')) and i + 1 < len(lines):
            # URLだけを保持し、展開プレビューをスキップ
            cleaned_lines.append(line)
            
            # 次の数行がプレビューと思われる場合はスキップ
            j = i + 1
            while j < len(lines) and not lines[j].strip().startswith(('http', 'https', '１', '１.', '1.', '1', '２', '２.', '2.', '2', '３', '３.', '3.', '3', '４', '４.', '4.', '4')):
                j += 1
            
            skip_next = j - i - 1
        else:
            cleaned_lines.append(line)
    
    # 修正したテキストを再構成
    post = '\n'.join(cleaned_lines)
    
    # 余分な空行を削除
    post = re.sub(r'\n\s*\n+', '\n\n', post)
    
    # (編集済み) などの編集マークを削除
    post = re.sub(r'（編集済み）|\(編集済み\)', '', post)
    
    return post.strip()

def analyze_single_post(content, model):
    """
    単一の投稿を解析する関数
    """
    prompt = f"""
    以下のSlackの自己紹介投稿を解析し、JSONオブジェクト形式だけで出力してください。
    説明文や前置きは一切不要です。整形済みのJSONだけを返してください。

    出力形式:
    {{
      "name": "名前",
      "projects": ["プロジェクト1", "プロジェクト2"],
      "expertise": ["得意なこと1", "得意なこと2"],
      "github": "GitHubアドレスまたは空文字列"
    }}

    投稿:
    {content}
    """
    
    result = query_ollama(model, prompt)
    
    try:
        # JSON部分の抽出を試みる
        json_text = extract_json(result)
        response = json.loads(json_text)
        return {
            "success": True,
            "data": response
        }
    except json.JSONDecodeError as e:
        print(f"JSONデコードエラー: {e}")
        print("抽出されたJSON文字列:")
        print(json_text)
        
        # JSON修復を試みる
        try:
            fixed_json = repair_json(json_text)
            response = json.loads(fixed_json)
            return {
                "success": True,
                "data": response
            }
        except Exception as e2:
            return {
                "success": False,
                "error": f"{str(e)}、修復後: {str(e2)}",
                "raw_response": result
            }

def extract_json(text):
    """
    テキストから JSON 部分を抽出する関数
    """
    # {}で囲まれた部分を探す
    match = re.search(r'\{[\s\S]*\}', text)
    if match:
        return match.group(0)
    return text  # JSONが見つからない場合は元のテキストを返す

def repair_json(text):
    """
    壊れたJSONを修復する
    """
    # 明らかな構文エラーを修正
    text = text.strip()
    
    # かぎ括弧がない場合は追加
    if not text.startswith('{'):
        text = '{' + text
    if not text.endswith('}'):
        text = text + '}'
    
    # キーと値のペアをチェック
    lines = text.split('\n')
    fixed_lines = []
    
    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue
            
        # キーがクォートされていない場合
        if ':' in line and not line.startswith('"') and not line.startswith('}'):
            key = line.split(':', 1)[0].strip()
            value = line.split(':', 1)[1].strip()
            line = f'"{key}": {value}'
        
        # 値がクォートされていないが文字列の場合
        if ':' in line and not line.endswith(',') and not line.endswith('}'):
            if i < len(lines) - 1 and not lines[i+1].strip().startswith('{') and not lines[i+1].strip().startswith('['):
                line = line + ','
        
        # リストの各要素でカンマがない場合
        if line.strip().startswith('"') and not line.endswith(',') and not line.endswith(']') and not line.endswith('}'):
            if i < len(lines) - 1 and not lines[i+1].strip().startswith(']') and not lines[i+1].strip().startswith('}'):
                line = line + ','
                
        fixed_lines.append(line)
    
    # 修正したJSONを再構成
    return '\n'.join(fixed_lines)

def parse_slack_posts(file_path):
    """
    Slackからコピーした自己紹介投稿を解析する関数
    """
    # 自己紹介投稿を抽出
    posts = extract_posts_from_slack(file_path)
    
    model = get_local_llm("local:pakachan/elyza-llama3-8b:latest")
    results = []
    
    for i, post in enumerate(posts):
        print(f"===== 投稿 {i+1}/{len(posts)} の解析中 =====")
        print(f"投稿内容（最初の150文字）: {post[:150].replace('\n', ' ')}...")
        result = analyze_single_post(post, model)
        
        if result["success"]:
            print(f"解析成功:")
            print(json.dumps(result["data"], indent=2, ensure_ascii=False))
            results.append(result["data"])
        else:
            print(f"解析失敗: {result['error']}")
            print("AIの応答:")
            print(result["raw_response"][:200] + "...")
        
        print("\n")
    
    # 全ての結果をJSONファイルに保存
    output_dir = os.path.dirname(file_path)
    output_path = os.path.join(output_dir, "analysis_results.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print(f"解析結果を {output_path} に保存しました。成功件数: {len(results)}/{len(posts)}")
    return results

# データを取得して標準出力に出力
if __name__ == "__main__":
    parse_slack_posts("post2.txt")