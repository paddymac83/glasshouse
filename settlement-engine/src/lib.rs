//! Glasshouse settlement engine.
//!
//! Computes a transparent, line-item bill for a half-hourly settlement
//! period, given a portfolio of generators (each with an available
//! volume and a cost) and a portfolio of consumers (each with a demand).
//!
//! The model deliberately does *not* try to route specific electrons from
//! specific generators to specific consumers -- that's not how an
//! electricity grid physically works. Instead it mirrors how "direct"
//! generator-to-business matching actually works commercially: a
//! merit-order stack decides which generation is used and at what
//! blended cost, and every consumer's bill is built transparently from
//! that blended cost plus network charges, policy costs, and a platform
//! margin -- with no cost lost or invented in the process.
//!
//! This module is usable two ways:
//!   - as a plain Rust library (`cargo test` exercises it directly, no
//!     Python involved)
//!   - as a Python extension module, built with `python-ext` enabled via
//!     maturin (see `python/README.md`)

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};

// ---------------------------------------------------------------------
// Domain types
// ---------------------------------------------------------------------

#[derive(Debug, Clone, PartialEq)]
pub struct Generator {
    pub id: String,
    pub available_mwh: f64,
    pub cost_gbp_per_mwh: f64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct Consumer {
    pub id: String,
    pub demand_mwh: f64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct BillLine {
    pub label: String,
    pub amount_gbp: f64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct ConsumerBill {
    pub consumer_id: String,
    pub lines: Vec<BillLine>,
    pub total_gbp: f64,
}

#[derive(Debug, Clone, Copy)]
pub struct TariffAssumptions {
    pub network_charge_gbp_per_mwh: f64,
    pub policy_cost_gbp_per_mwh: f64,
    pub platform_margin_fraction: f64,
}

#[derive(Debug, Clone)]
pub struct SettlementResult {
    pub bills: Vec<ConsumerBill>,
    pub unmet_demand_mwh: f64,
    pub blended_generation_price_gbp_per_mwh: f64,
}

#[derive(Debug, Clone, PartialEq)]
pub enum SettlementError {
    NoConsumers,
    NoDemand,
    NegativeInput(&'static str),
}

impl std::fmt::Display for SettlementError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            SettlementError::NoConsumers => write!(f, "at least one consumer is required"),
            SettlementError::NoDemand => write!(f, "total consumer demand must be greater than zero"),
            SettlementError::NegativeInput(field) => {
                write!(f, "negative values are not allowed for {field}")
            }
        }
    }
}

impl std::error::Error for SettlementError {}

// ---------------------------------------------------------------------
// Core allocation logic
// ---------------------------------------------------------------------

/// Round to the nearest penny. Bill lines are rounded individually and a
/// bill's total is the *sum of its rounded lines* -- never a separately
/// rounded subtotal -- so a bill always adds up exactly, to the penny.
fn round2(value: f64) -> f64 {
    (value * 100.0).round() / 100.0
}

pub fn settle_period(
    generators: &[Generator],
    consumers: &[Consumer],
    assumptions: TariffAssumptions,
) -> Result<SettlementResult, SettlementError> {
    if consumers.is_empty() {
        return Err(SettlementError::NoConsumers);
    }
    for g in generators {
        if g.available_mwh < 0.0 {
            return Err(SettlementError::NegativeInput("generator.available_mwh"));
        }
        if g.cost_gbp_per_mwh < 0.0 {
            return Err(SettlementError::NegativeInput("generator.cost_gbp_per_mwh"));
        }
    }
    for c in consumers {
        if c.demand_mwh < 0.0 {
            return Err(SettlementError::NegativeInput("consumer.demand_mwh"));
        }
    }
    if assumptions.network_charge_gbp_per_mwh < 0.0 {
        return Err(SettlementError::NegativeInput("network_charge_gbp_per_mwh"));
    }
    if assumptions.policy_cost_gbp_per_mwh < 0.0 {
        return Err(SettlementError::NegativeInput("policy_cost_gbp_per_mwh"));
    }
    if assumptions.platform_margin_fraction < 0.0 {
        return Err(SettlementError::NegativeInput("platform_margin_fraction"));
    }

    let total_demand_mwh: f64 = consumers.iter().map(|c| c.demand_mwh).sum();
    if total_demand_mwh <= 0.0 {
        return Err(SettlementError::NoDemand);
    }

    // Merit order: cheapest generation dispatched first.
    let mut merit_order: Vec<&Generator> = generators.iter().collect();
    merit_order.sort_by(|a, b| a.cost_gbp_per_mwh.partial_cmp(&b.cost_gbp_per_mwh).unwrap());

    let mut remaining_demand = total_demand_mwh;
    let mut total_allocated_mwh = 0.0_f64;
    let mut total_generation_cost_gbp = 0.0_f64;

    for generator in merit_order {
        if remaining_demand <= 0.0 {
            break;
        }
        let take = generator.available_mwh.min(remaining_demand);
        total_allocated_mwh += take;
        total_generation_cost_gbp += take * generator.cost_gbp_per_mwh;
        remaining_demand -= take;
    }

    let unmet_demand_mwh = remaining_demand.max(0.0);
    let served_demand_mwh = total_demand_mwh - unmet_demand_mwh;
    let blended_generation_price_gbp_per_mwh = if total_allocated_mwh > 0.0 {
        total_generation_cost_gbp / total_allocated_mwh
    } else {
        0.0
    };

    // Fair-share curtailment: if supply falls short, every consumer's
    // served volume shrinks by the same proportion. Nobody gets
    // silently prioritised over anybody else.
    let service_ratio = if total_demand_mwh > 0.0 {
        served_demand_mwh / total_demand_mwh
    } else {
        0.0
    };

    let bills = consumers
        .iter()
        .map(|consumer| {
            let served_mwh = consumer.demand_mwh * service_ratio;

            let generation_line = round2(served_mwh * blended_generation_price_gbp_per_mwh);
            let network_line = round2(served_mwh * assumptions.network_charge_gbp_per_mwh);
            let policy_line = round2(served_mwh * assumptions.policy_cost_gbp_per_mwh);
            let pre_margin_subtotal = generation_line + network_line + policy_line;
            let margin_line = round2(pre_margin_subtotal * assumptions.platform_margin_fraction);

            let lines = vec![
                BillLine { label: "Generation".to_string(), amount_gbp: generation_line },
                BillLine { label: "Network charges".to_string(), amount_gbp: network_line },
                BillLine { label: "Policy costs".to_string(), amount_gbp: policy_line },
                BillLine { label: "Platform margin".to_string(), amount_gbp: margin_line },
            ];
            let total_gbp = round2(lines.iter().map(|l| l.amount_gbp).sum());

            ConsumerBill { consumer_id: consumer.id.clone(), lines, total_gbp }
        })
        .collect();

    Ok(SettlementResult {
        bills,
        unmet_demand_mwh,
        blended_generation_price_gbp_per_mwh,
    })
}

// ---------------------------------------------------------------------
// Python bridge
// ---------------------------------------------------------------------

/// Python-facing entry point. Generators are `(id, available_mwh,
/// cost_gbp_per_mwh)` tuples; consumers are `(id, demand_mwh)` tuples.
/// Returns a plain dict so the FastAPI layer can `jsonify` it directly.
#[pyfunction]
#[pyo3(signature = (
    generators,
    consumers,
    network_charge_gbp_per_mwh,
    policy_cost_gbp_per_mwh,
    platform_margin_fraction
))]
fn settle_period_py(
    py: Python<'_>,
    generators: Vec<(String, f64, f64)>,
    consumers: Vec<(String, f64)>,
    network_charge_gbp_per_mwh: f64,
    policy_cost_gbp_per_mwh: f64,
    platform_margin_fraction: f64,
) -> PyResult<PyObject> {
    let gens: Vec<Generator> = generators
        .into_iter()
        .map(|(id, available_mwh, cost_gbp_per_mwh)| Generator { id, available_mwh, cost_gbp_per_mwh })
        .collect();
    let cons: Vec<Consumer> = consumers
        .into_iter()
        .map(|(id, demand_mwh)| Consumer { id, demand_mwh })
        .collect();
    let assumptions = TariffAssumptions {
        network_charge_gbp_per_mwh,
        policy_cost_gbp_per_mwh,
        platform_margin_fraction,
    };

    let result = settle_period(&gens, &cons, assumptions)
        .map_err(|e| PyValueError::new_err(e.to_string()))?;

    let out = PyDict::new_bound(py);
    out.set_item("unmet_demand_mwh", result.unmet_demand_mwh)?;
    out.set_item(
        "blended_generation_price_gbp_per_mwh",
        result.blended_generation_price_gbp_per_mwh,
    )?;

    let bills = PyList::empty_bound(py);
    for bill in result.bills {
        let bill_dict = PyDict::new_bound(py);
        bill_dict.set_item("consumer_id", &bill.consumer_id)?;
        bill_dict.set_item("total_gbp", bill.total_gbp)?;

        let lines = PyList::empty_bound(py);
        for line in &bill.lines {
            let line_dict = PyDict::new_bound(py);
            line_dict.set_item("label", &line.label)?;
            line_dict.set_item("amount_gbp", line.amount_gbp)?;
            lines.append(line_dict)?;
        }
        bill_dict.set_item("lines", lines)?;
        bills.append(bill_dict)?;
    }
    out.set_item("bills", bills)?;

    Ok(out.into())
}

#[pymodule]
fn glasshouse_settlement(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(settle_period_py, m)?)?;
    Ok(())
}

// ---------------------------------------------------------------------
// Tests -- pure Rust, no Python required. Run with `cargo test`.
// ---------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    fn assumptions() -> TariffAssumptions {
        TariffAssumptions {
            network_charge_gbp_per_mwh: 20.0,
            policy_cost_gbp_per_mwh: 15.0,
            platform_margin_fraction: 0.05,
        }
    }

    #[test]
    fn merit_order_dispatches_cheapest_generator_first() {
        let generators = vec![
            Generator { id: "gas".into(), available_mwh: 100.0, cost_gbp_per_mwh: 80.0 },
            Generator { id: "wind".into(), available_mwh: 10.0, cost_gbp_per_mwh: 30.0 },
        ];
        let consumers = vec![Consumer { id: "factory".into(), demand_mwh: 10.0 }];

        let result = settle_period(&generators, &consumers, assumptions()).unwrap();

        // Wind is cheaper and covers the entire 10 MWh of demand, so the
        // blended price should equal wind's cost, not a mix with gas.
        assert_eq!(result.blended_generation_price_gbp_per_mwh, 30.0);
        assert_eq!(result.unmet_demand_mwh, 0.0);
    }

    #[test]
    fn blends_across_generators_once_the_cheapest_is_exhausted() {
        let generators = vec![
            Generator { id: "gas".into(), available_mwh: 100.0, cost_gbp_per_mwh: 80.0 },
            Generator { id: "wind".into(), available_mwh: 5.0, cost_gbp_per_mwh: 30.0 },
        ];
        let consumers = vec![Consumer { id: "factory".into(), demand_mwh: 10.0 }];

        let result = settle_period(&generators, &consumers, assumptions()).unwrap();

        // 5 MWh at 30 + 5 MWh at 80, blended over 10 MWh = 55.0
        assert!((result.blended_generation_price_gbp_per_mwh - 55.0).abs() < 1e-9);
    }

    #[test]
    fn bills_scale_with_each_consumers_share_of_demand() {
        let generators = vec![Generator { id: "solar".into(), available_mwh: 100.0, cost_gbp_per_mwh: 40.0 }];
        let consumers = vec![
            Consumer { id: "small_shop".into(), demand_mwh: 2.0 },
            Consumer { id: "big_factory".into(), demand_mwh: 8.0 },
        ];

        let result = settle_period(&generators, &consumers, assumptions()).unwrap();

        let small = result.bills.iter().find(|b| b.consumer_id == "small_shop").unwrap();
        let big = result.bills.iter().find(|b| b.consumer_id == "big_factory").unwrap();

        // Big factory uses 4x the energy, so should pay ~4x the total.
        assert!((big.total_gbp - small.total_gbp * 4.0).abs() < 0.05);
    }

    #[test]
    fn shortfall_curtails_every_consumer_by_the_same_proportion() {
        let generators = vec![Generator { id: "wind".into(), available_mwh: 5.0, cost_gbp_per_mwh: 30.0 }];
        let consumers = vec![
            Consumer { id: "a".into(), demand_mwh: 6.0 },
            Consumer { id: "b".into(), demand_mwh: 4.0 },
        ];
        // Total demand 10 MWh, only 5 MWh available -> 50% service ratio.

        let result = settle_period(&generators, &consumers, assumptions()).unwrap();

        assert_eq!(result.unmet_demand_mwh, 5.0);
        let a = result.bills.iter().find(|b| b.consumer_id == "a").unwrap();
        let b = result.bills.iter().find(|b| b.consumer_id == "b").unwrap();
        // a:b demand ratio is 6:4, so their bills should keep that ratio.
        assert!((a.total_gbp / b.total_gbp - 1.5).abs() < 0.01);
    }

    #[test]
    fn every_bill_line_is_non_negative_and_totals_are_internally_consistent() {
        let generators = vec![Generator { id: "solar".into(), available_mwh: 50.0, cost_gbp_per_mwh: 45.0 }];
        let consumers = vec![
            Consumer { id: "a".into(), demand_mwh: 3.3 },
            Consumer { id: "b".into(), demand_mwh: 7.7 },
        ];

        let result = settle_period(&generators, &consumers, assumptions()).unwrap();

        for bill in &result.bills {
            let sum_of_lines: f64 = bill.lines.iter().map(|l| l.amount_gbp).sum();
            for line in &bill.lines {
                assert!(line.amount_gbp >= 0.0, "{} had a negative line", bill.consumer_id);
            }
            // The whole point of rounding lines first and summing them
            // (rather than rounding a subtotal) is that this holds exactly.
            assert!((bill.total_gbp - round2(sum_of_lines)).abs() < 1e-9);
        }
    }

    #[test]
    fn rejects_empty_consumer_list() {
        let generators = vec![Generator { id: "solar".into(), available_mwh: 50.0, cost_gbp_per_mwh: 45.0 }];
        let result = settle_period(&generators, &[], assumptions());
        assert_eq!(result.unwrap_err(), SettlementError::NoConsumers);
    }

    #[test]
    fn rejects_zero_total_demand() {
        let generators = vec![Generator { id: "solar".into(), available_mwh: 50.0, cost_gbp_per_mwh: 45.0 }];
        let consumers = vec![Consumer { id: "a".into(), demand_mwh: 0.0 }];
        let result = settle_period(&generators, &consumers, assumptions());
        assert_eq!(result.unwrap_err(), SettlementError::NoDemand);
    }

    #[test]
    fn rejects_negative_generator_cost() {
        let generators = vec![Generator { id: "solar".into(), available_mwh: 50.0, cost_gbp_per_mwh: -1.0 }];
        let consumers = vec![Consumer { id: "a".into(), demand_mwh: 5.0 }];
        let result = settle_period(&generators, &consumers, assumptions());
        assert_eq!(result.unwrap_err(), SettlementError::NegativeInput("generator.cost_gbp_per_mwh"));
    }

    #[test]
    fn zero_generators_means_fully_unmet_demand() {
        let consumers = vec![Consumer { id: "a".into(), demand_mwh: 5.0 }];
        let result = settle_period(&[], &consumers, assumptions()).unwrap();
        assert_eq!(result.unmet_demand_mwh, 5.0);
        assert_eq!(result.bills[0].total_gbp, 0.0);
    }
}
