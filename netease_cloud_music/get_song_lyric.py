import requests
import json

def get_lyric(song_id):
    headers = {
            "user-agent":"Mozilla/5.0",
            "Referer":"http://music.163.com",
            "Host":"music.163.com"
            }
    if not isinstance(song_id,str):
        song_id = str(song_id)
    url = f"http://music.163.com/api/song/lyric?id={song_id}+&lv=1&tv=-1"
    r = requests.get(url,headers=headers)
    r.raise_for_status()
    r.encoding = r.apparent_encoding
    json_obj = json.loads(r.text)
    lyric = json_obj['lrc']['lyric']
    #print(type(lyric))
    return lyric


# if __name__ == "__main__":

