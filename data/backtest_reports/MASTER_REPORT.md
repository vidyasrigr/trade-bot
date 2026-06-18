# Master Validation Report

Generated: 2026-06-18T01:49:31.097894
Elapsed: 22.2 min

## Verdicts at a glance

| Signal | Variant | Train DSR | WF DSR | Train n | WF n | Verdict |
|---|---|---|---|---|---|---|
| momentum_12_1 | momentum_12_1_lookback=252 | +0.023 | +0.527 | 830 | 320 | 🟡 SANDBOX |
| momentum_12_1 | momentum_12_1_lookback=189 | +0.003 | +0.600 | 836 | 320 | 🟡 SANDBOX |
| momentum_12_1 | momentum_12_1_lookback=126 | +0.354 | +0.307 | 840 | 320 | 🟡 SANDBOX |
| momentum_12_1 | momentum_12_1_lookback=63 | +0.236 | +0.047 | 840 | 320 | 🟡 SANDBOX |
| skew_25d | skew_25d_hold=21d | +0.006 | +0.752 | 136 | 70 | 🟡 SANDBOX |
| skew_25d | skew_25d_hold=42d | +0.000 | +0.469 | 122 | 66 | 🟡 SANDBOX |
| pead | pead_hold=5d | — | — | 0 | 0 | 🔴 BLOCKED |
| pead | pead_hold=10d | — | — | 0 | 0 | 🔴 BLOCKED |
| insider_opportunistic | insider_cluster_30d | — | — | 0 | 0 | 🔴 BLOCKED |
| lead_lag | lead_lag_60d_window | — | — | 0 | 0 | 🔴 BLOCKED |
| short_squeeze | squeeze_drechsler | — | — | 0 | 0 | 🔴 BLOCKED |
| vrp_harvest | vrp_naked_strangle_baseline | +0.904 | +0.317 | 526 | 215 | ✅ PROMOTE |
| vrp_harvest | vrp_iron_condor_wings=1.5sigma | +0.000 | +0.000 | 331 | 153 | 🟡 SANDBOX |
| vrp_harvest | vrp_iron_condor_wings=2.0sigma | +0.000 | +0.000 | 300 | 153 | 🟡 SANDBOX |
| vrp_harvest | vrp_iron_condor_wings=2.5sigma | +0.000 | +0.000 | 277 | 153 | 🟡 SANDBOX |
| vrp_harvest | vrp_iron_condor_wings=3.0sigma | +0.000 | +0.000 | 243 | 153 | 🟡 SANDBOX |
| vrp_harvest | vrp_naked_stop=1.0x | +0.887 | +0.312 | 526 | 215 | ✅ PROMOTE |
| vrp_harvest | vrp_naked_stop=1.5x | +0.897 | +0.004 | 170 | 13 | 🟡 SANDBOX |

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
    - num_trades: 136
    - win_rate: 0.47058823529411764
    - total_pnl: -6914.781596213777
    - sharpe: -0.7705220054146279
    - deflated_sharpe: 0.005867768855209792
    - max_drawdown: 0.22668408104840557
    - expectancy: -0.0050843982325101305
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
    - num_trades: 122
    - win_rate: 0.45901639344262296
    - total_pnl: -18812.004880889377
    - sharpe: -1.5402438556831115
    - deflated_sharpe: 0.0001553871939175267
    - max_drawdown: 0.43981292453875065
    - expectancy: -0.015419676131876541
- walk_forward:
    - num_trades: 66
    - win_rate: 0.5151515151515151
    - total_pnl: 15330.311408305095
    - sharpe: 1.659875729385511
    - deflated_sharpe: 0.468791221187355
    - max_drawdown: 0.03792201434625694
    - expectancy: 0.023227744558038027

### pead — pead_hold=5d

- Status: **blocked**
- Config: `{"hold_days": 5, "min_eps_surprise_pct": 5.0, "max_mkt_cap_b": 50, "universe": "liquid_1000"}`
- train:
    - num_trades: 0
- walk_forward:
    - num_trades: 0

### pead — pead_hold=10d

- Status: **blocked**
- Config: `{"hold_days": 10, "min_eps_surprise_pct": 5.0, "max_mkt_cap_b": 50, "universe": "liquid_1000"}`
- train:
    - num_trades: 0
- walk_forward:
    - num_trades: 0

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

- Status: **done**
- Config: `{"variant": "naked", "iv_rank_min": 50, "vrp_z_min": 1.0, "profit_target": 0.5, "stop_loss": 2.0, "short_delta": 0.16}`
- train:
    - num_trades: 526
    - win_rate: 0.6844106463878327
    - total_pnl: 245302.90000000008
    - sharpe: 2.5234120212263655
    - deflated_sharpe: 0.9036420434670536
    - max_drawdown: 0.27165717232274417
    - expectancy: 466.3553231939165
- walk_forward:
    - num_trades: 215
    - win_rate: 0.6697674418604651
    - total_pnl: 151697.5
    - sharpe: 1.394897868353436
    - deflated_sharpe: 0.31677190789734155
    - max_drawdown: 0.5108130181247784
    - expectancy: 705.5697674418604

### vrp_harvest — vrp_iron_condor_wings=1.5sigma

- Status: **sandboxed**
- Config: `{"variant": "iron_condor", "wings_sigma": 1.5, "iv_rank_min": 50, "vrp_z_min": 1.0, "profit_target": 0.5, "stop_loss": 2.0, "short_delta": 0.16}`
- train:
    - num_trades: 331
    - win_rate: 0.27492447129909364
    - total_pnl: -32869.2
    - sharpe: -9.8842943014322
    - deflated_sharpe: 1.8474692639207535e-62
    - max_drawdown: 0.3287846277213698
    - expectancy: -99.30271903323262
- walk_forward:
    - num_trades: 153
    - win_rate: 0.24836601307189543
    - total_pnl: -12848.6
    - sharpe: -8.08276684177605
    - deflated_sharpe: 9.811609127851203e-10
    - max_drawdown: 0.128458110659539
    - expectancy: -83.97777777777777

### vrp_harvest — vrp_iron_condor_wings=2.0sigma

- Status: **sandboxed**
- Config: `{"variant": "iron_condor", "wings_sigma": 2.0, "iv_rank_min": 50, "vrp_z_min": 1.0, "profit_target": 0.5, "stop_loss": 2.0, "short_delta": 0.16}`
- train:
    - num_trades: 300
    - win_rate: 0.4033333333333333
    - total_pnl: -29599.750000000007
    - sharpe: -9.168886397987405
    - deflated_sharpe: 8.817729891449735e-47
    - max_drawdown: 0.2962406488558154
    - expectancy: -98.66583333333335
- walk_forward:
    - num_trades: 153
    - win_rate: 0.42483660130718953
    - total_pnl: -12120.1
    - sharpe: -6.476346406235995
    - deflated_sharpe: 5.315854643825453e-09
    - max_drawdown: 0.12144919060365247
    - expectancy: -79.21633986928104

### vrp_harvest — vrp_iron_condor_wings=2.5sigma

- Status: **sandboxed**
- Config: `{"variant": "iron_condor", "wings_sigma": 2.5, "iv_rank_min": 50, "vrp_z_min": 1.0, "profit_target": 0.5, "stop_loss": 2.0, "short_delta": 0.16}`
- train:
    - num_trades: 277
    - win_rate: 0.45126353790613716
    - total_pnl: -31596.650000000005
    - sharpe: -8.204733836194624
    - deflated_sharpe: 1.0965305895484954e-29
    - max_drawdown: 0.3165519605305583
    - expectancy: -114.06732851985561
- walk_forward:
    - num_trades: 153
    - win_rate: 0.48366013071895425
    - total_pnl: -13989.6
    - sharpe: -4.567776550385985
    - deflated_sharpe: 5.5494441681855314e-08
    - max_drawdown: 0.1472366978228278
    - expectancy: -91.43529411764706

### vrp_harvest — vrp_iron_condor_wings=3.0sigma

- Status: **sandboxed**
- Config: `{"variant": "iron_condor", "wings_sigma": 3.0, "iv_rank_min": 50, "vrp_z_min": 1.0, "profit_target": 0.5, "stop_loss": 2.0, "short_delta": 0.16}`
- train:
    - num_trades: 243
    - win_rate: 0.4567901234567901
    - total_pnl: -29779.6
    - sharpe: -6.952916677246306
    - deflated_sharpe: 1.5656186720240817e-23
    - max_drawdown: 0.30041071495285954
    - expectancy: -122.54979423868312
- walk_forward:
    - num_trades: 153
    - win_rate: 0.5032679738562091
    - total_pnl: -13018.850000000002
    - sharpe: -3.54805091797703
    - deflated_sharpe: 3.48882977632059e-06
    - max_drawdown: 0.15960298594353647
    - expectancy: -85.090522875817

### vrp_harvest — vrp_naked_stop=1.0x

- Status: **done**
- Config: `{"variant": "naked", "iv_rank_min": 50, "vrp_z_min": 1.0, "profit_target": 0.5, "stop_loss": 1.0, "short_delta": 0.16}`
- train:
    - num_trades: 526
    - win_rate: 0.629277566539924
    - total_pnl: 238675.65000000008
    - sharpe: 2.402211648391743
    - deflated_sharpe: 0.8867986134419846
    - max_drawdown: 0.2778484626432994
    - expectancy: 453.7559885931561
- walk_forward:
    - num_trades: 215
    - win_rate: 0.6232558139534884
    - total_pnl: 147443.75
    - sharpe: 1.3781380709427475
    - deflated_sharpe: 0.31158086146924446
    - max_drawdown: 0.5275388553272086
    - expectancy: 685.7848837209302

### vrp_harvest — vrp_naked_stop=1.5x

- Status: **sandboxed**
- Config: `{"variant": "naked", "iv_rank_min": 50, "vrp_z_min": 1.0, "profit_target": 0.5, "stop_loss": 1.5, "short_delta": 0.16}`
- train:
    - num_trades: 170
    - win_rate: 0.7470588235294118
    - total_pnl: 17205.499999999996
    - sharpe: 3.3267849884456346
    - deflated_sharpe: 0.8974973434741629
    - max_drawdown: 0.023909030136813593
    - expectancy: 101.20882352941175
- walk_forward:
    - num_trades: 13
    - win_rate: 0.6153846153846154
    - total_pnl: -863.3
    - sharpe: -3.418258676914064
    - deflated_sharpe: 0.004141685106984052
    - max_drawdown: 0.017426527269103216
    - expectancy: -66.4076923076923

## Recommended actions

Per V's validation ladder (DSR > 0.5 train AND > 0.3 walk-forward → PROMOTE):

- **Promote to paper trading:** ['vrp_naked_strangle_baseline', 'vrp_naked_stop=1.0x']
- **Sandbox (observe only):** ['momentum_12_1_lookback=252', 'momentum_12_1_lookback=189', 'momentum_12_1_lookback=126', 'momentum_12_1_lookback=63', 'skew_25d_hold=21d', 'skew_25d_hold=42d', 'vrp_iron_condor_wings=1.5sigma', 'vrp_iron_condor_wings=2.0sigma', 'vrp_iron_condor_wings=2.5sigma', 'vrp_iron_condor_wings=3.0sigma', 'vrp_naked_stop=1.5x']
- **Blocked (needs harness/data fix):** ['pead_hold=5d', 'pead_hold=10d', 'insider_cluster_30d', 'lead_lag_60d_window', 'squeeze_drechsler']
- **Errored (investigate):** NONE