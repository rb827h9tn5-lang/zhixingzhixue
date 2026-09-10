
Add-Type -AssemblyName System.Speech
$s=New-Object System.Speech.Synthesis.SpeechSynthesizer
$s.SelectVoice('Microsoft Huihui Desktop')
$s.SetOutputToWaveFile('.t/w.wav')
$s.Speak('小智同学')
$s.Dispose()
