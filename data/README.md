# Synthetic sales data

**This data is synthetic.** The company (PT Kalaraya Seduh Indonesia), the brand (Kalaraya Coffee), its stores and its products are all fictional. Store names use real Indonesian neighbourhoods only to sound natural. Any match with a real business is a coincidence.

It is a coffee-shop chain with 46 stores in 6 regions of Indonesia. It sells drinks, food, beans and merchandise in its stores and through a delivery app. Prices are per item, in rupiah.

Regenerate with `python3 generator/generate.py` (seed `20261108`; same seed and end date give the same files). Check it with `python3 eval/check_dataset.py`.

## Tables

| File | Grain | Key columns |
|---|---|---|
| `fact_sales.parquet` | One product, store, channel and day | `date`, `store_id`, `product_id`, `channel`, `qty`, `unit_price`, `gross_amount`, `discount_amount`, `net_amount` |
| `fact_orders.parquet` | One store, channel and day | `date`, `store_id`, `channel`, `orders`, `items` |
| `dim_store.parquet` | One store | `store_id`, `store_name`, `city`, `region`, `format` (Street, Mall, Office), `open_date`, `event_id` |
| `dim_product.parquet` | One product | `product_id`, `product_name`, `category`, `temperature`, `list_price_2024` |
| `dim_date.parquet` | One day | `date`, `year_week` (ISO), `week_start`, `holiday`, `is_ramadan`, `is_lebaran_holiday`, `is_rainy_season` |
| `events.json` | One planted event | What happened, where, when, and by how much |

Data runs from 1 Jan 2024 to 1 Nov 2026 (ISO week 2026-W44).

## What is in the data
- **Growth:** 5–10% a year in the same stores, by region. Menu prices rise 8% (Jan 2025) and 5% (Jan 2026), rounded to Rp1,000.
- **Store formats:** office stores are busy on weekdays and quiet at weekends and on public holidays; mall stores peak at weekends.
- **Delivery app:** about a quarter of sales, with a 10% merchant-funded discount.
- **Payday:** about 6% more sales from the 25th to the 3rd.
- **Rainy season (November to March):** fewer iced drinks, more hot drinks and more delivery.
- **Ramadan and Lebaran:** in-store sales fall during Ramadan while delivery rises. Stores close on the first day of Idul Fitri. During the Lebaran holiday Jabodetabek sales drop by about half and other regions rise. Holiday dates follow the SKB 3 Menteri for 2024–2026.
- **December:** malls busier before Christmas; office stores quiet in the last week.
- **Planted events (E1–E8):** new stores, a price rise, a delivery-app promotion, a store renovation, a stock-out, a new competitor, a product promotion and floods. `events.json` lists them, so the agent's findings can be checked against the truth.

## Not modelled
- Individual receipts, refunds and staff meals.
- Public holidays other than Lebaran, 1 January, 17 August and 25 December.
- Calibration to real market figures. Sizes are plausible, not measured.
