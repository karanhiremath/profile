defmodule CaiAos.MixProject do
  use Mix.Project

  def project do
    [
      app: :cai_aos,
      version: "0.1.0",
      elixir: "~> 1.17",
      start_permanent: Mix.env() == :prod,
      deps: []
    ]
  end

  def application do
    [
      extra_applications: [:logger],
      mod: {CaiAos.Application, []}
    ]
  end
end
