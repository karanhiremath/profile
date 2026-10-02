defmodule CaiAos.SpendTest do
  use ExUnit.Case, async: true

  test "prices grok fast and slow on all token buckets" do
    fast =
      CaiAos.Spend.evaluate(%{
        model: "cursor/grok-4.6:fast",
        input: 500_000,
        output: 250_000,
        cache_read: 200_000,
        cache_write: 50_000
      })

    assert fast.classified == "grok-4.6:fast"
    assert fast.cost.usd_per_m == 1.45
    assert_in_delta fast.cost.total, 1.45, 1.0e-9
    assert fast.gate == "go"

    slow =
      CaiAos.Spend.evaluate(%{
        model: "grok-4.6:slow",
        input: 1_000_000,
        output: 0,
        cache_read: 0,
        cache_write: 0
      })

    assert slow.cost.usd_per_m == 0.68
    assert_in_delta slow.cost.total, 0.68, 1.0e-9
  end

  test "gates a weekly cap" do
    result =
      CaiAos.Spend.evaluate(
        %{model: "grok-4.6:fast", input: 1_000_000, weekly_usd: 2.0},
        %{"windows" => %{"cursor" => %{"weekly_usd" => 3.0}}}
      )

    assert result.gate == "no-go"
    assert result.window.over_weekly
  end

  test "prices dashboard grok-fast CSV rows" do
    result =
      CaiAos.Spend.CursorCsv.evaluate(%{
        "Model" => "cursor-grok-4.6-xhigh-fast",
        "Input (w/ Cache Write)" => "0",
        "Input (w/o Cache Write)" => "500000",
        "Cache Read" => "200000",
        "Output Tokens" => "50000",
        "Total Tokens" => "750000",
        "Cost" => "Free"
      })

    assert result.classified == "grok-4.6:fast"
    assert result.tokens.input == 500_000
    assert result.tokens.cache_read == 200_000
    assert result.tokens.billed == 750_000
    assert_in_delta result.cost.total, 1.45 * 0.75, 1.0e-9
  end

  test "prices Together DeepSeek V4 Flash 0731 by bucket" do
    result =
      CaiAos.Spend.evaluate(%{
        model: "together/deepseek-ai/DeepSeek-V4-Flash-0731",
        input: 1_000_000,
        output: 1_000_000,
        cache_read: 1_000_000,
        cache_write: 0
      })

    assert result.classified == "deepseek-v4-flash-0731"
    assert_in_delta result.cost.input, 0.14, 1.0e-9
    assert_in_delta result.cost.output, 0.28, 1.0e-9
    assert_in_delta result.cost.cache_read, 0.03, 1.0e-9
    assert_in_delta result.cost.total, 0.45, 1.0e-9
  end
end
