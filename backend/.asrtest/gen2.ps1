Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$s.SelectVoice("Microsoft Huihui Desktop")
$s.Rate = 0
$s.SetOutputToWaveFile("$PWD\short1.wav"); $s.Speak("打开测评"); 
$s.SetOutputToWaveFile("$PWD\short2.wav"); $s.Speak("打开思维导图");
$s.SetOutputToWaveFile("$PWD\long1.wav"); $s.Speak("小智同学，帮我打开学习路径页面，然后我想看看我的学习画像");
$s.Dispose()
