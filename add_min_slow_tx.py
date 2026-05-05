#!/usr/bin/env python3
path = '/data/lumen/frontend/index.html'

with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Genel Ayarlar kartina min_slow_tx_count ekle
old = "settingInput('min_tx_count','Min. TX Sayisi',s['min_tx_count'],'Minimum islem sayisi') +"
new = (
    "settingInput('min_tx_count','Min. TX Sayisi',s['min_tx_count'],'Anomali icin minimum islem sayisi') +\n"
    "      settingInput('min_slow_tx_count','Min. Yavas TX',s['min_slow_tx_count'],'Elapsed anomali icin minimum yavas islem sayisi') +"
)

if old in content:
    content = content.replace(old, new)
    print('OK: min_slow_tx_count alani eklendi')
else:
    print('WARN: Genel ayarlar satiri bulunamadi')

# saveAnomSettings key listesine ekle
old_keys = "['min_tx_count','cooldown_seconds','sliding_window_seconds','rule_elapsed_p99_disaster','rule_elapsed_p95_high','rule_elapsed_disaster','rule_elapsed_high','rule_error_rate_disaster','rule_error_rate_high','sys_error_code_threshold','biz_error_code_threshold']"
new_keys = "['min_tx_count','min_slow_tx_count','cooldown_seconds','sliding_window_seconds','rule_elapsed_p99_disaster','rule_elapsed_p95_high','rule_elapsed_disaster','rule_elapsed_high','rule_error_rate_disaster','rule_error_rate_high','sys_error_code_threshold','biz_error_code_threshold']"

if old_keys in content:
    content = content.replace(old_keys, new_keys)
    print('OK: saveAnomSettings key listesi guncellendi')
else:
    print('WARN: saveAnomSettings key listesi bulunamadi')

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

print('Tamamlandi')
