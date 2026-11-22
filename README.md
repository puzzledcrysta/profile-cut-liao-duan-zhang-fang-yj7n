# 料段账房

门窗加工车间备料员可用本地工作台处理锯切计划，复查料段去向并与独立清单逐笔核对。

按订单长料优先，从最紧合的可用余料分配，计入锯缝并区分可复用料尾和报废。

## 启动

```sh
docker compose up --build
```

打开 http://127.0.0.1:18303 并运行随附样例。可以在「导入来源与外部账」上传自己的 CSV，也可以编辑表单中的样例。数据保存于 Compose 卷 `ledger`。使用 `APP_PORT` 可覆盖宿主端口。

## 工作步骤

1. 检查「备料凭证」与「型材规格」，定位导入坏行与字段归一结果。
2. 在「异常计划」区分冲突、业务拒绝、重传与旧版本。
3. 打开「型材排料」并点击任意记录的「查看依据」。
4. 在「领料核对」检查金额或用量差异。通过「锯切批次」复算原文件，通过「班组复核」提交意见并下载证据。
5. 在「料尾台账」登记退料，决定预占留给原签批批次还是借给等料急单；领用按领料单号幂等扣减，归还按借出单恢复一次。

接口定义见 `/openapi.json`。字段、允许区间及算例见 [数据字典](docs/DATA-DICTIONARY.md)，模块和回归测试见 [测试登记](docs/DEPTH.md)。

## 验证

```sh
docker compose config --quiet
docker compose exec -T app pytest -q
```

`sample_data/shift.csv` 是班次数据，`sample_data/external.csv` 是独立账样例。`cases.csv` 固定业务反例，`legacy.csv` 和 `truncated.csv` 用于验证历史格式与断行。
