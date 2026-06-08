#!/usr/bin/env python3
import json, os, base64, tempfile
from datetime import datetime, timezone, timedelta

TW = timezone(timedelta(hours=8))
now = datetime.now(TW)
today = now.strftime('%Y-%m-%d')
print(f"執行時間：{now.strftime('%Y-%m-%d %H:%M:%S')} (台灣時間)")

SECTORS = [
    {"name":"半導體","stocks":[
        {"symbol":"2330","name":"台積電"},{"symbol":"2454","name":"聯發科"},
        {"symbol":"2303","name":"聯電"},{"symbol":"2379","name":"瑞昱"},
        {"symbol":"3711","name":"日月光"}]},
    {"name":"電子","stocks":[
        {"symbol":"2317","name":"鴻海"},{"symbol":"2382","name":"廣達"},
        {"symbol":"2308","name":"台達電"},{"symbol":"2354","name":"鴻準"},
        {"symbol":"2357","name":"華碩"}]},
    {"name":"金融","stocks":[
        {"symbol":"2881","name":"富邦金"},{"symbol":"2882","name":"國泰金"},
        {"symbol":"2891","name":"中信金"},{"symbol":"2886","name":"兆豐金"},
        {"symbol":"2884","name":"玉山金"}]},
    {"name":"光電","stocks":[
        {"symbol":"2409","name":"友達"},{"symbol":"3481","name":"群創"},
        {"symbol":"6669","name":"緯穎"},{"symbol":"2498","name":"宏達電"},
        {"symbol":"3673","name":"TPK"}]},
    {"name":"生技","stocks":[
        {"symbol":"4763","name":"台灣神隆"},{"symbol":"6547","name":"聯合骨科"},
        {"symbol":"4726","name":"永日"},{"symbol":"3707","name":"漢磊"},
        {"symbol":"1795","name":"美時"}]},
]

def fetch():
    from fubon_neo.sdk import FubonSDK

    cert_b64 = os.environ["FUBON_CERT_B64"]
    cert_b64 += "=" * (4 - len(cert_b64) % 4)
    cert_data = base64.b64decode(cert_b64)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pfx")
    tmp.write(cert_data)
    tmp.close()
    cert_path = tmp.name
