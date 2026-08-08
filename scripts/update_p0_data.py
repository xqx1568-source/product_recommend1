#!/usr/bin/env python3
"""Generate the GitHub Pages data.csv for the P0 assortment page.

Default input is an Aeolus CSV export from report rid=6082893. In Aime, pass the
latest downloaded file with --input, then commit docs/data.csv.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

try:
    import pandas as pd
except Exception as exc:  # pragma: no cover
    raise SystemExit("pandas is required: pip install pandas") from exc

CN_TZ = timezone(timedelta(hours=8))

SOURCE_COLUMNS = {
    "country": "product_avaliable_country",
    "pid": "product_id",
    "spu": "spu_code",
    "shop": "supplier_name",
    "cate2": "second_category_name",
    "cate3": "third_category_name",
    "score": "final_score",
    "image": "image_url",
    "first_listed": "[PID] first_success_audit_date",
    "stock": "avail_prodlive_stock_cnt_td",
    "gmv_1d": "当日支付gmv（美元）",
    "orders_1d": "最近1天支付子单数（剔除样品单）",
    "content_gmv": "内容场交易额",
    "gmv_7d": "近7天支付gmv-usd",
    "gmv_7d_delta": "近7天环比GMV",
    "orders_7d": "近7日支付子单量",
    "orders_7d_delta": "近7天销量环比值",
    "pv_7d": "最近7天商品曝光pv",
    "pv_7d_delta": "近7天曝光环比值",
    "ctr": "近7天ctr",
    "cvr": "近7天CO",
    "gpm": "近7天GPM",
    "opm": "近7天OPM",
    "gmv_30d": "近30天支付gmv-usd",
    "orders_30d": "近30日支付子单量",
    "total_orders": "累计支付子单量",
    "video_gmv_1d": "近1天短视频支付金额-usd 流量口径  content_type = video",
    "live_gmv_1d": "近1天直播间支付金额-usd 流量口径  content_type = live",
    "video_order_share": "短视频销量占比",
    "live_order_share": "直播销量占比",
    "asp_7d": "近7天ASP",
    "price": "list_price_usd",
    "max_price": "max_list_price",
    "quantity": "plm_prop_quantity",
    "color": "plm_prop_color_type",
    "size": "plm_prop_size_type",
    "lifecycle": "product_lifecycle_tag_t1",
    "p0": "P0冷启成功商品渗透率",
    "pdp_urls": "prd_product_urls",
    "jit": "has_jit_sku",
    "combo": "has_combo_sku",
    "high_comp": "is_high_comp",
}

OUTPUT_COLUMNS = [
    "推荐优先级", "国家", "ProductID", "SPU Code", "店铺/供应商", "二级类目", "三级类目",
    "P0丰富度标签", "增速分级", "销量标签", "效率标签", "生命周期", "商品首图URL", "商品详情页URL",
    "近7天GMV(USD)", "近7天环比GMV(USD)", "近30天GMV(USD)", "近7天销量", "近7天销量环比",
    "近7天ASP", "标价(USD)", "可用库存", "平均评分", "短视频销量占比", "直播销量占比",
    "近7天CTR", "近7天CVR", "近7天GPM", "近7天OPM", "件数", "颜色", "尺码",
    "JIT货盘", "组合SKU", "高竞争", "推荐理由", "数据来源", "生成时间"
]


def to_num(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        if isinstance(value, float) and math.isnan(value):
            return default
        text = str(value).strip().replace(",", "")
        if text in {"", "nan", "NaN", "NULL", "None", "/"}:
            return default
        return float(text)
    except Exception:
        return default


def clean(value: Any, fallback: str = "/") -> str:
    if value is None:
        return fallback
    if isinstance(value, float) and math.isnan(value):
        return fallback
    text = str(value).strip()
    if not text or text.lower() == "nan" or text == "NULL":
        return fallback
    return text


def money(value: Any) -> str:
    return f"{to_num(value):.2f}"


def pct(value: Any) -> str:
    return f"{to_num(value) * 100:.1f}%"


def sales_bucket(orders: float) -> str:
    if orders >= 500:
        return "500+"
    if orders >= 100:
        return "100+"
    if orders >= 50:
        return "50+"
    if orders >= 10:
        return "10+"
    if orders >= 1:
        return "破0件"
    return "/"


def growth_bucket(delta_gmv: float) -> str:
    if delta_gmv >= 5000:
        return "爆发增长"
    if delta_gmv >= 2000:
        return "高增长"
    if delta_gmv >= 500:
        return "中增长"
    if delta_gmv >= 0:
        return "增长"
    return "待观察"


def p0_label(value: Any) -> str:
    return "丰富度P0" if to_num(value) == 1 else "非P0补充"


def efficiency_tags(ctr: float, cvr: float, gpm: float) -> str:
    tags = []
    if ctr > 0.02:
        tags.append("高点击")
    if cvr > 0.02:
        tags.append("高转化")
    if gpm > 2:
        tags.append("高变现")
    return "+".join(tags) if tags else "效率待观察"


def pdp_url(urls: Any, country: str) -> str:
    text = clean(urls, "")
    if not text:
        return "/"
    try:
        parsed = json.loads(text)
        if country in parsed:
            return parsed[country]
        if parsed:
            return next(iter(parsed.values()))
    except Exception:
        pass
    return text if text.startswith("http") else "/"


def priority(row: pd.Series) -> str:
    p0 = to_num(row.get(SOURCE_COLUMNS["p0"])) == 1
    delta = to_num(row.get(SOURCE_COLUMNS["gmv_7d_delta"]))
    score = to_num(row.get(SOURCE_COLUMNS["score"]))
    stock = to_num(row.get(SOURCE_COLUMNS["stock"]))
    if p0 and delta >= 2000 and score >= 4.5 and stock >= 100:
        return "S级优先"
    if p0 and delta >= 500 and stock > 0:
        return "A级推荐"
    if delta >= 0 and stock > 0:
        return "B级观察"
    return "C级补充"


def reason(row: pd.Series) -> str:
    parts = [
        p0_label(row.get(SOURCE_COLUMNS["p0"])),
        growth_bucket(to_num(row.get(SOURCE_COLUMNS["gmv_7d_delta"]))),
        f"{sales_bucket(to_num(row.get(SOURCE_COLUMNS['orders_7d'])))}销量",
        efficiency_tags(to_num(row.get(SOURCE_COLUMNS["ctr"])), to_num(row.get(SOURCE_COLUMNS["cvr"])), to_num(row.get(SOURCE_COLUMNS["gpm"])))
    ]
    return "｜".join(parts)


def build(input_path: Path, output_path: Path, limit: int) -> None:
    df = pd.read_csv(input_path, dtype=str, keep_default_na=False)
    for required in [SOURCE_COLUMNS["pid"], SOURCE_COLUMNS["gmv_7d_delta"]]:
        if required not in df.columns:
            raise SystemExit(f"Missing required column: {required}")

    mask = (
        df[SOURCE_COLUMNS["pid"]].astype(str).str.len().gt(0)
        & pd.to_numeric(df[SOURCE_COLUMNS["score"]], errors="coerce").fillna(0).ge(3.8)
        & pd.to_numeric(df[SOURCE_COLUMNS["stock"]], errors="coerce").fillna(0).gt(0)
        & pd.to_numeric(df[SOURCE_COLUMNS["orders_7d"]], errors="coerce").fillna(0).gt(0)
    )
    df = df.loc[mask].copy()
    df["_sort"] = pd.to_numeric(df[SOURCE_COLUMNS["gmv_7d_delta"]], errors="coerce").fillna(0)
    df = df.sort_values("_sort", ascending=False).drop_duplicates(subset=[SOURCE_COLUMNS["pid"]]).head(limit)

    generated_at = datetime.now(CN_TZ).strftime("%Y-%m-%d %H:%M")
    rows = []
    for _, row in df.iterrows():
        country = clean(row.get(SOURCE_COLUMNS["country"]))
        rows.append({
            "推荐优先级": priority(row),
            "国家": country,
            "ProductID": clean(row.get(SOURCE_COLUMNS["pid"])),
            "SPU Code": clean(row.get(SOURCE_COLUMNS["spu"])),
            "店铺/供应商": clean(row.get(SOURCE_COLUMNS["shop"])),
            "二级类目": clean(row.get(SOURCE_COLUMNS["cate2"])),
            "三级类目": clean(row.get(SOURCE_COLUMNS["cate3"])),
            "P0丰富度标签": p0_label(row.get(SOURCE_COLUMNS["p0"])),
            "增速分级": growth_bucket(to_num(row.get(SOURCE_COLUMNS["gmv_7d_delta"]))),
            "销量标签": sales_bucket(to_num(row.get(SOURCE_COLUMNS["orders_7d"]))),
            "效率标签": efficiency_tags(to_num(row.get(SOURCE_COLUMNS["ctr"])), to_num(row.get(SOURCE_COLUMNS["cvr"])), to_num(row.get(SOURCE_COLUMNS["gpm"]))),
            "生命周期": clean(row.get(SOURCE_COLUMNS["lifecycle"])),
            "商品首图URL": clean(row.get(SOURCE_COLUMNS["image"])),
            "商品详情页URL": pdp_url(row.get(SOURCE_COLUMNS["pdp_urls"]), country),
            "近7天GMV(USD)": money(row.get(SOURCE_COLUMNS["gmv_7d"])),
            "近7天环比GMV(USD)": money(row.get(SOURCE_COLUMNS["gmv_7d_delta"])),
            "近30天GMV(USD)": money(row.get(SOURCE_COLUMNS["gmv_30d"])),
            "近7天销量": str(int(to_num(row.get(SOURCE_COLUMNS["orders_7d"])))),
            "近7天销量环比": str(int(to_num(row.get(SOURCE_COLUMNS["orders_7d_delta"])))),
            "近7天ASP": money(row.get(SOURCE_COLUMNS["asp_7d"])),
            "标价(USD)": money(row.get(SOURCE_COLUMNS["price"])),
            "可用库存": str(int(to_num(row.get(SOURCE_COLUMNS["stock"])))),
            "平均评分": f"{to_num(row.get(SOURCE_COLUMNS['score'])):.1f}",
            "短视频销量占比": pct(row.get(SOURCE_COLUMNS["video_order_share"])),
            "直播销量占比": pct(row.get(SOURCE_COLUMNS["live_order_share"])),
            "近7天CTR": pct(row.get(SOURCE_COLUMNS["ctr"])),
            "近7天CVR": pct(row.get(SOURCE_COLUMNS["cvr"])),
            "近7天GPM": f"{to_num(row.get(SOURCE_COLUMNS['gpm'])):.2f}",
            "近7天OPM": f"{to_num(row.get(SOURCE_COLUMNS['opm'])):.2f}",
            "件数": clean(row.get(SOURCE_COLUMNS["quantity"])),
            "颜色": clean(row.get(SOURCE_COLUMNS["color"])),
            "尺码": clean(row.get(SOURCE_COLUMNS["size"])),
            "JIT货盘": "是" if to_num(row.get(SOURCE_COLUMNS["jit"])) == 1 else "否",
            "组合SKU": "是" if to_num(row.get(SOURCE_COLUMNS["combo"])) == 1 else "否",
            "高竞争": "是" if to_num(row.get(SOURCE_COLUMNS["high_comp"])) == 1 else "否",
            "推荐理由": reason(row),
            "数据来源": "Aeolus rid=6082893 / sid=3062689",
            "生成时间": generated_at,
        })

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows -> {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Aeolus CSV export path")
    parser.add_argument("--output", default="docs/data.csv")
    parser.add_argument("--limit", type=int, default=999)
    args = parser.parse_args()
    build(Path(args.input), Path(args.output), args.limit)


if __name__ == "__main__":
    main()
