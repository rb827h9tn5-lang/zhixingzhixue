"""探测 MIMO ASR 能力，用于确定语音助手实现方案。用完即删。"""
import base64, json, os, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor
import urllib.request

BASE = "https://fufu.iqach.top"
KEY = os.environ["MIMO_KEY"]
HERE = os.path.dirname(os.path.abspath(__file__))


def gen_wav(name, text, rate=0):
    path = os.path.join(HERE, name)
    ps = (
        "Add-Type -AssemblyName System.Speech; "
        "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        "$s.SelectVoice('Microsoft Huihui Desktop'); "
        f"$s.Rate={rate}; "
        f"$s.SetOutputToWaveFile('{path}'); $s.Speak('{text}'); $s.Dispose()"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                   capture_output=True)
    return path


def asr(path, fmt="wav"):
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    body = json.dumps({
        "model": "mimo-v2.5-asr",
        "messages": [{"role": "user", "content": [
            {"type": "input_audio", "input_audio": {"data": b64, "format": fmt}}
        ]}],
    }).encode()
    req = urllib.request.Request(
        f"{BASE}/v1/chat/completions", data=body,
        headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
    )
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            d = json.loads(r.read())
        txt = d["choices"][0]["message"]["content"]
        return round((time.time() - t0) * 1000), txt, None
    except Exception as e:
        detail = ""
        if hasattr(e, "read"):
            detail = e.read()[:200].decode("utf-8", "replace")
        return round((time.time() - t0) * 1000), None, f"{type(e).__name__}: {e} {detail}"


def show(label, path, fmt="wav"):
    ms, txt, err = asr(path, fmt)
    size = os.path.getsize(path) if os.path.exists(path) else 0
    print(f"  [{label}] {ms}ms  {size}B  ->  {txt!r}{'  ERR=' + err if err else ''}", flush=True)
    return ms, txt


print("=== 生成测试音频 ===", flush=True)
clips = {
    "wake":   gen_wav("p_wake.wav", "小智同学"),
    "cmd":    gen_wav("p_cmd.wav", "打开测评"),
    "mind":   gen_wav("p_mind.wav", "打开思维导图"),
    "combo":  gen_wav("p_combo.wav", "小智同学，打开学习路径"),
    "long":   gen_wav("p_long.wav", "小智同学，帮我打开学习路径，我还想看看我的学习画像"),
}
for k, v in clips.items():
    print(f"  {k}: {os.path.getsize(v)}B", flush=True)

print("\n=== 1. 各长度音频的延迟 ===", flush=True)
lat = {}
for k in ["wake", "cmd", "mind", "combo", "long"]:
    ms, _ = show(k, clips[k])
    lat[k] = ms

print("\n=== 2. 静音 / 噪音返回什么(决定如何过滤空说话) ===", flush=True)
# 生成 2 秒纯静音 wav
import struct, wave
sil = os.path.join(HERE, "p_silence.wav")
with wave.open(sil, "w") as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
    w.writeframes(b"\x00\x00" * 16000 * 2)
show("silence-2s", sil)

print("\n=== 3. 并发 3 路(持续监听要靠并发压延迟) ===", flush=True)
t0 = time.time()
with ThreadPoolExecutor(max_workers=3) as ex:
    futs = [ex.submit(asr, clips["cmd"]) for _ in range(3)]
    res = [f.result() for f in futs]
total = round((time.time() - t0) * 1000)
print(f"  3 路并发总耗时 {total}ms (串行应约 {sum(lat.get('cmd', 0) for _ in range(3))}ms)", flush=True)
for i, (ms, txt, err) in enumerate(res, 1):
    print(f"    路{i}: {ms}ms {txt!r} {err or ''}", flush=True)

print("\n=== 4. 音频格式支持(决定前端录音方式) ===", flush=True)
for fmt in ["wav", "mp3", "webm", "pcm16", "ogg"]:
    ms, txt, err = asr(clips["cmd"], fmt)
    ok = "OK" if txt else "FAIL"
    print(f"  format={fmt:<7} {ok:<5} {ms}ms {txt!r} {(err or '')[:120]}", flush=True)

print("\n=== 5. 真 webm/opus 文件(前端 MediaRecorder 的实际产物) ===", flush=True)
webm = os.path.join(HERE, "p_cmd.webm")
r = subprocess.run(["ffmpeg", "-y", "-i", clips["cmd"], "-c:a", "libopus", webm],
                   capture_output=True)
if os.path.exists(webm):
    for fmt in ["webm", "opus"]:
        ms, txt, err = asr(webm, fmt)
        print(f"  真webm as {fmt}: {txt!r} {(err or '')[:120]}", flush=True)
else:
    print("  ffmpeg 不可用，跳过（前端可改用 wav 编码）", flush=True)
