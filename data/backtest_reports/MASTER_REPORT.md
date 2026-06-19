# Master Validation Report

Generated: 2026-06-19T05:26:41.034384
Elapsed: 12.1 min

## Verdicts at a glance

| Signal | Variant | Train DSR | WF DSR | Train n | WF n | Verdict |
|---|---|---|---|---|---|---|
| momentum_12_1 | momentum_12_1_lookback=252 | +0.023 | +0.527 | 830 | 320 | 🟡 SANDBOX |
| momentum_12_1 | momentum_12_1_lookback=189 | +0.003 | +0.600 | 836 | 320 | 🟡 SANDBOX |
| momentum_12_1 | momentum_12_1_lookback=126 | +0.354 | +0.307 | 840 | 320 | 🟡 SANDBOX |
| momentum_12_1 | momentum_12_1_lookback=63 | +0.236 | +0.047 | 840 | 320 | 🟡 SANDBOX |
| skew_25d | skew_25d_hold=21d | +0.002 | +0.752 | 236 | 70 | 🟡 SANDBOX |
| skew_25d | skew_25d_hold=42d | +0.000 | +0.581 | 236 | 66 | 🟡 SANDBOX |
| pead | pead_hold=5d | +0.073 | +0.204 | 333 | 135 | 🟡 SANDBOX |
| pead | pead_hold=10d | +0.554 | +0.252 | 333 | 135 | 🟡 SANDBOX |
| insider_opportunistic | insider_cluster_30d | — | — | 0 | 0 | 🔴 BLOCKED |
| lead_lag | lead_lag_60d_window | — | — | 0 | 0 | 🔴 BLOCKED |
| short_squeeze | squeeze_drechsler | — | — | 0 | 0 | 🔴 BLOCKED |
| vrp_harvest | vrp_naked_strangle_baseline | +0.843 | +0.309 | 1052 | 430 | 🟡 SANDBOX |
| vrp_harvest | vrp_iron_condor_wings=1.5sigma | +0.000 | +0.000 | 694 | 301 | 🟡 SANDBOX |
| vrp_harvest | vrp_iron_condor_wings=2.0sigma | +0.000 | +0.000 | 695 | 301 | 🟡 SANDBOX |
| vrp_harvest | vrp_iron_condor_wings=2.5sigma | +0.000 | +0.000 | 696 | 301 | 🟡 SANDBOX |
| vrp_harvest | vrp_iron_condor_wings=3.0sigma | +0.000 | +0.000 | 696 | 301 | 🟡 SANDBOX |
| vrp_harvest | vrp_regime_gate_ratio=1.3 | +0.580 | +0.301 | 877 | 330 | 🟡 SANDBOX |
| vrp_harvest | vrp_regime_gate_ratio=1.5 | +0.739 | +0.304 | 978 | 364 | 🟡 SANDBOX |
| vrp_harvest | vrp_naked_stop=1.0x | +0.802 | +0.301 | 1052 | 430 | 🟡 SANDBOX |
| vrp_harvest | vrp_naked_stop=1.5x | +0.820 | +0.316 | 1052 | 430 | 🟡 SANDBOX |

## Detail per variant

### momentum_12_1 — momentum_12_1_lookback=252

- Status: **sandboxed**
- Config: `{"lookback_days": 252, "rebalance_days": 21, "universe": "liquid_1000"}`
- train:
    - num_trades: 830
    - win_rate: 0.5421686746987951
    - total_pnl: -23787.12504530263
    - sharpe: -0.1233439425480779
    - deflated_sharpe: 0.022744056264350835
    - max_drawdown: 0.6776625267603285
    - expectancy: -0.00286591868015694
- walk_forward:
    - num_trades: 320
    - win_rate: 0.546875
    - total_pnl: 145333.1001702445
    - sharpe: 1.5770214505647773
    - deflated_sharpe: 0.5269415018267054
    - max_drawdown: 0.29117552074313463
    - expectancy: 0.0454165938032014

### momentum_12_1 — momentum_12_1_lookback=189

- Status: **sandboxed**
- Config: `{"lookback_days": 189, "rebalance_days": 21, "universe": "liquid_1000"}`
- train:
    - num_trades: 836
    - win_rate: 0.507177033492823
    - total_pnl: -88662.2437942965
    - sharpe: -0.43803730402220475
    - deflated_sharpe: 0.003415141322754331
    - max_drawdown: 0.8869890985385803
    - expectancy: -0.01060553155434169
- walk_forward:
    - num_trades: 320
    - win_rate: 0.553125
    - total_pnl: 145485.29341767525
    - sharpe: 1.4601395843809535
    - deflated_sharpe: 0.5996915482933014
    - max_drawdown: 0.17782794427891022
    - expectancy: 0.04546415419302351

### momentum_12_1 — momentum_12_1_lookback=126

- Status: **sandboxed**
- Config: `{"lookback_days": 126, "rebalance_days": 21, "universe": "liquid_1000"}`
- train:
    - num_trades: 840
    - win_rate: 0.5214285714285715
    - total_pnl: 118108.78574026759
    - sharpe: 0.7454637574942309
    - deflated_sharpe: 0.3537873715720451
    - max_drawdown: 0.3013951082400191
    - expectancy: 0.014060569730984237
- walk_forward:
    - num_trades: 320
    - win_rate: 0.53125
    - total_pnl: 75023.87353961701
    - sharpe: 1.1338771052011467
    - deflated_sharpe: 0.30693154326722316
    - max_drawdown: 0.1436598332791973
    - expectancy: 0.023444960481130317

### momentum_12_1 — momentum_12_1_lookback=63

- Status: **sandboxed**
- Config: `{"lookback_days": 63, "rebalance_days": 21, "universe": "liquid_1000"}`
- train:
    - num_trades: 840
    - win_rate: 0.5011904761904762
    - total_pnl: 83328.17610119199
    - sharpe: 0.5813433117944707
    - deflated_sharpe: 0.23631777820979022
    - max_drawdown: 0.3928942661470535
    - expectancy: 0.00992002096442762
- walk_forward:
    - num_trades: 320
    - win_rate: 0.515625
    - total_pnl: 8434.268769628547
    - sharpe: 0.08262474713667406
    - deflated_sharpe: 0.04657967679377201
    - max_drawdown: 0.5191419484633114
    - expectancy: 0.0026357089905089197

### skew_25d — skew_25d_hold=21d

- Status: **sandboxed**
- Config: `{"hold_days": 21, "rebalance_days": 21, "quantile": 0.3, "universe": "liquid_1000"}`
- train:
    - num_trades: 236
    - win_rate: 0.4703389830508475
    - total_pnl: -15102.484151669187
    - sharpe: -0.9628344543661577
    - deflated_sharpe: 0.0016689276843361836
    - max_drawdown: 0.3661833037034564
    - expectancy: -0.006399357691385247
- walk_forward:
    - num_trades: 70
    - win_rate: 0.5857142857142857
    - total_pnl: 18585.897218715963
    - sharpe: 1.8772602386004302
    - deflated_sharpe: 0.7517047856477734
    - max_drawdown: 0.051821600433623265
    - expectancy: 0.02655128174102281

### skew_25d — skew_25d_hold=42d

- Status: **sandboxed**
- Config: `{"hold_days": 42, "rebalance_days": 21, "quantile": 0.3, "universe": "liquid_1000"}`
- train:
    - num_trades: 236
    - win_rate: 0.4533898305084746
    - total_pnl: -29574.426531631023
    - sharpe: -1.2038415184730429
    - deflated_sharpe: 0.0003466342453231819
    - max_drawdown: 0.4607415074208354
    - expectancy: -0.01253153666594535
- walk_forward:
    - num_trades: 66
    - win_rate: 0.5151515151515151
    - total_pnl: 17898.02591714489
    - sharpe: 1.8616590813383078
    - deflated_sharpe: 0.5808381858182043
    - max_drawdown: 0.03792201434625679
    - expectancy: 0.027118221086583166

### pead — pead_hold=5d

- Status: **sandboxed**
- Config: `{"hold_days": 5, "min_eps_surprise_pct": 5.0, "max_mkt_cap_b": 50, "universe": "liquid_1000"}`
- train:
    - num_trades: 333
    - win_rate: 0.4984984984984985
    - total_pnl: 4791.630034369096
    - sharpe: 0.11184462020391563
    - deflated_sharpe: 0.07310383941153563
    - max_drawdown: 0.7810236087218634
    - expectancy: 0.0014389279382489776
- walk_forward:
    - num_trades: 135
    - win_rate: 0.5481481481481482
    - total_pnl: 6831.664507978756
    - sharpe: 1.5561801503821404
    - deflated_sharpe: 0.2043082285359598
    - max_drawdown: 0.3473027592097723
    - expectancy: 0.005060492228132411

### pead — pead_hold=10d

- Status: **sandboxed**
- Config: `{"hold_days": 10, "min_eps_surprise_pct": 5.0, "max_mkt_cap_b": 50, "universe": "liquid_1000"}`
- train:
    - num_trades: 333
    - win_rate: 0.5285285285285285
    - total_pnl: 27135.571729271338
    - sharpe: 1.5363080895920187
    - deflated_sharpe: 0.5535377548777599
    - max_drawdown: 0.7933257611752683
    - expectancy: 0.008148820339120521
- walk_forward:
    - num_trades: 135
    - win_rate: 0.5555555555555556
    - total_pnl: 13219.955742872626
    - sharpe: 1.741151204180159
    - deflated_sharpe: 0.2515136569335903
    - max_drawdown: 0.5595183705011939
    - expectancy: 0.009792559809535277

### insider_opportunistic — insider_cluster_30d

- Status: **blocked**
- Config: `{"cluster_window_days": 30, "min_opportunistic": 3, "min_distinct_insiders": 2, "hold_days": 60, "universe": "liquid_1000"}`
- train:
    - num_trades: 0
- walk_forward:
    - num_trades: 0

### lead_lag — lead_lag_60d_window

- Status: **blocked**
- Config: `{"correlation_window_days": 60, "max_lag_days": 15, "min_abs_corr": 0.25, "universe": "liquid_500"}`
- train:
    - num_trades: 0
- walk_forward:
    - num_trades: 0

### short_squeeze — squeeze_drechsler

- Status: **blocked**
- Config: `{"si_pct_float_min": 0.15, "days_to_cover_min": 5.0, "hold_days": 30, "universe": "liquid_1000"}`
- train:
    - num_trades: 0
- walk_forward:
    - num_trades: 0

### vrp_harvest — vrp_naked_strangle_baseline

- Status: **sandboxed**
- Config: `{"variant": "naked", "iv_rank_min": 50, "vrp_z_min": 1.0, "profit_target": 0.5, "stop_loss": 2.0, "short_delta": 0.16}`
- train:
    - num_trades: 1052
    - win_rate: 0.6815589353612167
    - total_pnl: 228914.5500000001
    - sharpe: 1.8089437400670334
    - deflated_sharpe: 0.8433775541727366
    - max_drawdown: 0.5088079212723702
    - expectancy: 217.59938212927767
- walk_forward:
    - num_trades: 430
    - win_rate: 0.5930232558139535
    - total_pnl: 115062.2499999999
    - sharpe: 1.1540268359533485
    - deflated_sharpe: 0.30875259463650845
    - max_drawdown: 0.8242568976847392
    - expectancy: 267.5866279069765

### vrp_harvest — vrp_iron_condor_wings=1.5sigma

- Status: **sandboxed**
- Config: `{"variant": "iron_condor", "wings_sigma": 1.5, "iv_rank_min": 50, "vrp_z_min": 1.0, "profit_target": 0.5, "stop_loss": 2.0, "short_delta": 0.16}`
- train:
    - num_trades: 694
    - win_rate: 0.24495677233429394
    - total_pnl: -59115.3
    - sharpe: -10.035794571441466
    - deflated_sharpe: 6.782922618653155e-55
    - max_drawdown: 0.5911529999999932
    - expectancy: -85.18054755043228
- walk_forward:
    - num_trades: 301
    - win_rate: 0.18604651162790697
    - total_pnl: -37098.700000000004
    - sharpe: -9.90597731338787
    - deflated_sharpe: 1.9286205453201027e-27
    - max_drawdown: 0.37098700000000084
    - expectancy: -123.25149501661132

### vrp_harvest — vrp_iron_condor_wings=2.0sigma

- Status: **sandboxed**
- Config: `{"variant": "iron_condor", "wings_sigma": 2.0, "iv_rank_min": 50, "vrp_z_min": 1.0, "profit_target": 0.5, "stop_loss": 2.0, "short_delta": 0.16}`
- train:
    - num_trades: 695
    - win_rate: 0.34676258992805753
    - total_pnl: -54486.0
    - sharpe: -8.675494313283169
    - deflated_sharpe: 2.3829023684218554e-50
    - max_drawdown: 0.5452851557853277
    - expectancy: -78.39712230215828
- walk_forward:
    - num_trades: 301
    - win_rate: 0.3023255813953488
    - total_pnl: -36521.200000000004
    - sharpe: -8.618407631066827
    - deflated_sharpe: 7.738673760788599e-23
    - max_drawdown: 0.3652120000000009
    - expectancy: -121.33289036544852

### vrp_harvest — vrp_iron_condor_wings=2.5sigma

- Status: **sandboxed**
- Config: `{"variant": "iron_condor", "wings_sigma": 2.5, "iv_rank_min": 50, "vrp_z_min": 1.0, "profit_target": 0.5, "stop_loss": 2.0, "short_delta": 0.16}`
- train:
    - num_trades: 696
    - win_rate: 0.41810344827586204
    - total_pnl: -56372.450000000004
    - sharpe: -7.619724777758798
    - deflated_sharpe: 9.437376609905131e-50
    - max_drawdown: 0.565770999999993
    - expectancy: -80.99489942528736
- walk_forward:
    - num_trades: 301
    - win_rate: 0.36212624584717606
    - total_pnl: -40237.7
    - sharpe: -6.660399264926786
    - deflated_sharpe: 6.609064681105666e-19
    - max_drawdown: 0.4024352625619003
    - expectancy: -133.68006644518272

### vrp_harvest — vrp_iron_condor_wings=3.0sigma

- Status: **sandboxed**
- Config: `{"variant": "iron_condor", "wings_sigma": 3.0, "iv_rank_min": 50, "vrp_z_min": 1.0, "profit_target": 0.5, "stop_loss": 2.0, "short_delta": 0.16}`
- train:
    - num_trades: 696
    - win_rate: 0.45689655172413796
    - total_pnl: -53188.2
    - sharpe: -6.555154326748437
    - deflated_sharpe: 6.585329108303455e-38
    - max_drawdown: 0.5387769999999934
    - expectancy: -76.41982758620689
- walk_forward:
    - num_trades: 301
    - win_rate: 0.38205980066445183
    - total_pnl: -42436.7
    - sharpe: -5.375442912611569
    - deflated_sharpe: 4.526730062261239e-15
    - max_drawdown: 0.42447059529284653
    - expectancy: -140.98571428571427

### vrp_harvest — vrp_regime_gate_ratio=1.3

- Status: **sandboxed**
- Config: `{"variant": "regime", "stress_ratio": 1.3, "iv_rank_min": 50, "vrp_z_min": 1.0, "profit_target": 0.5, "stop_loss": 2.0, "short_delta": 0.16}`
- train:
    - num_trades: 877
    - win_rate: 0.661345496009122
    - total_pnl: 150818.55000000005
    - sharpe: 1.4127808052644486
    - deflated_sharpe: 0.580175616361593
    - max_drawdown: 0.5731034011767542
    - expectancy: 171.97098061573553
- walk_forward:
    - num_trades: 330
    - win_rate: 0.5515151515151515
    - total_pnl: 116652.24999999991
    - sharpe: 1.2110251797560725
    - deflated_sharpe: 0.3011636013049387
    - max_drawdown: 0.7816187564715743
    - expectancy: 353.4916666666664

### vrp_harvest — vrp_regime_gate_ratio=1.5

- Status: **sandboxed**
- Config: `{"variant": "regime", "stress_ratio": 1.5, "iv_rank_min": 50, "vrp_z_min": 1.0, "profit_target": 0.5, "stop_loss": 2.0, "short_delta": 0.16}`
- train:
    - num_trades: 978
    - win_rate: 0.6717791411042945
    - total_pnl: 190316.45
    - sharpe: 1.632000629203586
    - deflated_sharpe: 0.7388342350656772
    - max_drawdown: 0.5357255309151159
    - expectancy: 194.59759713701433
- walk_forward:
    - num_trades: 364
    - win_rate: 0.5714285714285714
    - total_pnl: 117383.09999999989
    - sharpe: 1.1708062753991417
    - deflated_sharpe: 0.3041406889800128
    - max_drawdown: 0.7910418618411319
    - expectancy: 322.48104395604366

### vrp_harvest — vrp_naked_stop=1.0x

- Status: **sandboxed**
- Config: `{"variant": "naked", "iv_rank_min": 50, "vrp_z_min": 1.0, "profit_target": 0.5, "stop_loss": 1.0, "short_delta": 0.16}`
- train:
    - num_trades: 1052
    - win_rate: 0.6178707224334601
    - total_pnl: 216062.5500000001
    - sharpe: 1.6906279255316012
    - deflated_sharpe: 0.8015842489819929
    - max_drawdown: 0.5162367385574189
    - expectancy: 205.38265209125484
- walk_forward:
    - num_trades: 430
    - win_rate: 0.5372093023255814
    - total_pnl: 116815.9999999999
    - sharpe: 1.1215731784539906
    - deflated_sharpe: 0.30079039325532386
    - max_drawdown: 0.7893939770222095
    - expectancy: 271.66511627906954

### vrp_harvest — vrp_naked_stop=1.5x

- Status: **sandboxed**
- Config: `{"variant": "naked", "iv_rank_min": 50, "vrp_z_min": 1.0, "profit_target": 0.5, "stop_loss": 1.5, "short_delta": 0.16}`
- train:
    - num_trades: 1052
    - win_rate: 0.6606463878326996
    - total_pnl: 221728.8000000001
    - sharpe: 1.760511887685486
    - deflated_sharpe: 0.8197204697452797
    - max_drawdown: 0.5142680534186593
    - expectancy: 210.76882129277575
- walk_forward:
    - num_trades: 430
    - win_rate: 0.5790697674418605
    - total_pnl: 112688.4999999999
    - sharpe: 1.1437156337193335
    - deflated_sharpe: 0.315500101873862
    - max_drawdown: 0.8668121420128234
    - expectancy: 262.0662790697672

## Recommended actions

Per V's validation ladder (DSR > 0.5 train AND > 0.3 walk-forward → PROMOTE):

- **Promote to paper trading:** NONE
- **Sandbox (observe only):** ['momentum_12_1_lookback=252', 'momentum_12_1_lookback=189', 'momentum_12_1_lookback=126', 'momentum_12_1_lookback=63', 'skew_25d_hold=21d', 'skew_25d_hold=42d', 'pead_hold=5d', 'pead_hold=10d', 'vrp_naked_strangle_baseline', 'vrp_iron_condor_wings=1.5sigma', 'vrp_iron_condor_wings=2.0sigma', 'vrp_iron_condor_wings=2.5sigma', 'vrp_iron_condor_wings=3.0sigma', 'vrp_regime_gate_ratio=1.3', 'vrp_regime_gate_ratio=1.5', 'vrp_naked_stop=1.0x', 'vrp_naked_stop=1.5x']
- **Blocked (needs harness/data fix):** ['insider_cluster_30d', 'lead_lag_60d_window', 'squeeze_drechsler']
- **Errored (investigate):** NONE