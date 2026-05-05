#!/usr/bin/env python3
path = '/data/lumen/frontend/index.html'

with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Elapsed Esikleri kartina p95/p99 ekle
old = "settingInput('rule_elapsed_disaster','DISASTER (ms)',s['rule_elapsed_disaster'],'') +"
new = (
    "settingInput('rule_elapsed_p99_disaster','p99 DISASTER (ms)',s['rule_elapsed_p99_disaster'],'Islemlerin %99u bu degeri gecerse DISASTER') +"
    "\n      settingInput('rule_elapsed_p95_high','p95 HIGH (ms)',s['rule_elapsed_p95_high'],'Islemlerin %95i bu degeri gecerse HIGH') +"
    "\n      settingInput('rule_elapsed_disaster','Max DISASTER (ms)',s['rule_elapsed_disaster'],'Eski max elapsed esigi') +"
)

if old in content:
    content = content.replace(old, new)
    print('OK: p95/p99 alanlari eklendi')
else:
    print('WARN: Elapsed esikleri satiri bulunamadi')

# saveAnomSettings'e p95/p99 key'leri ekle
old_keys = "['min_tx_count','cooldown_seconds','sliding_window_seconds','rule_elapsed_disaster','rule_elapsed_high','rule_error_rate_disaster','rule_error_rate_high','sys_error_code_threshold','biz_error_code_threshold']"
new_keys = "['min_tx_count','cooldown_seconds','sliding_window_seconds','rule_elapsed_p99_disaster','rule_elapsed_p95_high','rule_elapsed_disaster','rule_elapsed_high','rule_error_rate_disaster','rule_error_rate_high','sys_error_code_threshold','biz_error_code_threshold']"

if old_keys in content:
    content = content.replace(old_keys, new_keys)
    print('OK: saveAnomSettings key listesi guncellendi')
else:
    print('WARN: saveAnomSettings key listesi bulunamadi')

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

print('Tamamlandi')
