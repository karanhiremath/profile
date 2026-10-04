defmodule CosVoice.MixProject do
  use Mix.Project

  def project do
    [
      app: :cos_voice,
      version: "0.1.0",
      elixir: "~> 1.17",
      start_permanent: Mix.env() == :prod,
      deps: deps()
    ]
  end

  defp deps do
    [
      {:wasmex, "~> 0.15.1"}
    ]
  end

  def application do
    [
      extra_applications: [:logger],
      mod: {CosVoice.Application, []}
    ]
  end
end
