import json
import queue
import re
import requests
import datetime
from concurrent.futures import ThreadPoolExecutor
from jmcomic import JmOption

# 初始化 JM 客户端（放在全局，减少函数启动冷启动时间）
option = JmOption.default()
client = option.new_jm_client()
EH_API_URL = "https://api.e-hentai.org/api.php"

def search_jm_task(keyword, results):
    try:
        page = client.search_site(search_query=keyword, page=1)
        for album_id, info in page.content:
            try:
                if not isinstance(info, dict):
                    info = {"name": str(info), "id": album_id}
                
                update_date = ""
                ts = info.get('update_at')
                if ts:
                    dt = datetime.datetime.fromtimestamp(int(ts))
                    update_date = dt.strftime('%Y-%m-%d')

                results.append({
                    "platform": "jm",
                    "id": str(album_id),
                    "title": info.get('name', '未知标题'),
                    "author": info.get('author', '未知作者'),
                    "tags": [str(t.get('title') if isinstance(t, dict) else t) for t in info.get('tags', [])],
                    "update_date": update_date,
                    "cover": info.get('image') or f"https://cdn-msp.jmapiproxy1.cc/media/albums/{album_id}_3x4.jpg",
                    "url": f"https://18comic.vip/album/{album_id}"
                })
            except: continue
    except Exception as e:
        print(f"JM Error: {e}")

def search_eh_task(keyword, results):
    try:
        search_url = f"https://e-hentai.org/?f_search={keyword}&inline_set=dm_l"
        headers = {'User-Agent': 'Mozilla/5.0...'}
        response = requests.get(search_url, headers=headers, timeout=5)
        pattern = re.compile(r'https://e-hentai.org/g/(\d+)/([a-z0-9]+)/')
        matches = pattern.findall(response.text)
        
        if not matches: return

        gidlist = [[int(m[0]), m[1]] for m in matches[:15]] # 限制数量缩短搜索时长
        payload = {"method": "gdata", "gidlist": gidlist, "namespace": 1}
        api_res = requests.post(EH_API_URL, json=payload, timeout=5)
        data = api_res.json()
        
        for g in data.get('gmetadata', []):
            dt = datetime.datetime.fromtimestamp(int(g.get('posted', 0)))
            results.append({
                "platform": "eh",
                "id": str(g.get('gid')),
                "title": g.get('title_jp') or g.get('title'),
                "author": g.get('uploader', 'Unknown'),
                "tags": g.get('tags', [])[:8],
                "update_date": dt.strftime('%Y-%m-%d'),
                "cover": g.get('thumb'),
                "url": f"https://e-hentai.org/g/{g.get('gid')}/{g.get('token')}/"
            })
    except Exception as e:
        print(f"EH Error: {e}")

# Netlify 函数入口
def handler(event, context):
    # 允许跨域请求
    headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Content-Type",
        "Content-Type": "application/json"
    }
    
    keyword = event.get("queryStringParameters", {}).get("search")
    if not keyword:
        return {"statusCode": 400, "body": "Missing keyword"}

    all_results = []
    
    # 并行搜索
    with ThreadPoolExecutor(max_workers=5) as executor:
        executor.submit(search_jm_task, keyword, all_results)
        executor.submit(search_eh_task, keyword, all_results)

    # 模拟流式格式，但在 Serverless 中是一次性返回全部
    return {
        "statusCode": 200,
        "headers": headers,
        "body": json.dumps(all_results, ensure_ascii=False)
    }