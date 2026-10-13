# Setup Windows Scheduled Tasks for CAF-Terminal
$PythonPath = "C:\Users\WS\Desktop\antigravity\CAF\.venv\Scripts\python.exe"
$WorkingDir = "C:\Users\WS\Desktop\antigravity\CAF"

Write-Host "============================================================"
Write-Host "Регистрация регламентных задач CAF-Terminal в Windows"
Write-Host "============================================================"

# 1. Daily Sensor (Каждый день в 10:00)
$ActionDaily = New-ScheduledTaskAction -Execute $PythonPath -Argument "main.py --daily" -WorkingDirectory $WorkingDir
$TriggerDaily = New-ScheduledTaskTrigger -Daily -At "10:00AM"
$SettingsDaily = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
Register-ScheduledTask -TaskName "CAF_Daily_Sensor" -Action $ActionDaily -Trigger $TriggerDaily -Settings $SettingsDaily -Description "CAF-Terminal Ежедневный утренний сенсор аномалий и зон добора" -Force
Write-Host "[+] Зарегистрирована задача: CAF_Daily_Sensor (Ежедневно в 10:00)"

# 2. Weekly Radar & Committee (Каждое воскресенье в 20:00)
$ActionWeekly = New-ScheduledTaskAction -Execute $PythonPath -Argument "main.py --weekly --top 20" -WorkingDirectory $WorkingDir
$TriggerWeekly = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At "08:00PM"
Register-ScheduledTask -TaskName "CAF_Weekly_Radar" -Action $ActionWeekly -Trigger $TriggerWeekly -Settings $SettingsDaily -Description "CAF-Terminal Еженедельный Радар Топ-20 и Инвестиционный Комитет" -Force
Write-Host "[+] Зарегистрирована задача: CAF_Weekly_Radar (Каждое воскресенье в 20:00)"

# 3. Monthly Audit (1-е число каждого месяца в 11:00)
# В Windows Task Scheduler месячный триггер можно создать через schtasks
schtasks /create /tn "CAF_Monthly_Audit" /tr "`"$PythonPath`" main.py --audit" /sc monthly /d 1 /st 11:00 /f
Write-Host "[+] Зарегистрирована задача: CAF_Monthly_Audit (1-е число месяца в 11:00)"

# 4. Quarterly Rebalance (Каждые 3 месяца в 12:00)
schtasks /create /tn "CAF_Quarterly_Rebalance" /tr "`"$PythonPath`" main.py --rebalance" /sc monthly /mo 3 /d 1 /st 12:00 /f
Write-Host "[+] Зарегистрирована задача: CAF_Quarterly_Rebalance (Раз в квартал 1-го числа в 12:00)"

Write-Host "============================================================"
Write-Host "Все задачи успешно зарегистрированы в Планировщике Windows!"
Write-Host "============================================================"
