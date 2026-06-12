"use client";

interface Contract {
  strike: number;
  option_type: string;
  bid: number;
  ask: number;
  volume: number;
  open_interest: number;
  greeks?: {
    delta: number;
    gamma: number;
    theta: number;
    vega: number;
    mid_iv: number;
  };
  recommended?: boolean;
}

interface Props {
  chain: Contract[];
  lastPrice?: number;
}

export function OptionsChain({ chain, lastPrice }: Props) {
  const calls = chain.filter(c => c.option_type === "C").sort((a, b) => a.strike - b.strike);
  const puts  = chain.filter(c => c.option_type === "P").sort((a, b) => a.strike - b.strike);

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
      <div className="px-4 py-3 border-b border-gray-800">
        <h3 className="text-white font-semibold text-sm">Options Chain</h3>
        {lastPrice && (
          <div className="text-gray-400 text-xs mt-0.5">Last: ${lastPrice.toFixed(2)}</div>
        )}
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-gray-800">
              <td colSpan={6} className="px-3 py-2 text-green-400 font-medium text-center bg-green-900/10">CALLS</td>
              <td className="px-3 py-2 text-gray-400 font-medium text-center bg-gray-800">STRIKE</td>
              <td colSpan={6} className="px-3 py-2 text-red-400 font-medium text-center bg-red-900/10">PUTS</td>
            </tr>
            <tr className="text-gray-500 border-b border-gray-800">
              {["Bid", "Ask", "Vol", "OI", "Δ", "IV"].map(h => (
                <th key={h} className="px-2 py-1.5 font-normal text-right">{h}</th>
              ))}
              <th className="px-3 py-1.5 text-gray-300 font-semibold text-center">Strike</th>
              {["Bid", "Ask", "Vol", "OI", "Δ", "IV"].map(h => (
                <th key={h} className="px-2 py-1.5 font-normal text-right">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {calls.map((call, i) => {
              const put = puts.find(p => p.strike === call.strike);
              const isATM = lastPrice && Math.abs(call.strike - lastPrice) / lastPrice < 0.02;
              const rowClass = isATM ? "bg-gray-800/50" : "";
              const rec = call.recommended ? "ring-1 ring-green-500/50" : "";
              return (
                <tr key={call.strike} className={`border-b border-gray-800/50 ${rowClass} ${rec}`}>
                  <td className="px-2 py-1.5 text-right text-green-400">{call.bid?.toFixed(2)}</td>
                  <td className="px-2 py-1.5 text-right text-green-400">{call.ask?.toFixed(2)}</td>
                  <td className="px-2 py-1.5 text-right text-gray-400">{call.volume?.toLocaleString()}</td>
                  <td className="px-2 py-1.5 text-right text-gray-400">{call.open_interest?.toLocaleString()}</td>
                  <td className="px-2 py-1.5 text-right text-yellow-400">{call.greeks?.delta?.toFixed(2)}</td>
                  <td className="px-2 py-1.5 text-right text-blue-400">{call.greeks?.mid_iv ? `${(call.greeks.mid_iv * 100).toFixed(0)}%` : "—"}</td>

                  <td className={`px-3 py-1.5 text-center font-mono font-semibold ${isATM ? "text-white" : "text-gray-300"}`}>
                    {call.strike}
                  </td>

                  {put ? (
                    <>
                      <td className="px-2 py-1.5 text-right text-red-400">{put.bid?.toFixed(2)}</td>
                      <td className="px-2 py-1.5 text-right text-red-400">{put.ask?.toFixed(2)}</td>
                      <td className="px-2 py-1.5 text-right text-gray-400">{put.volume?.toLocaleString()}</td>
                      <td className="px-2 py-1.5 text-right text-gray-400">{put.open_interest?.toLocaleString()}</td>
                      <td className="px-2 py-1.5 text-right text-yellow-400">{put.greeks?.delta?.toFixed(2)}</td>
                      <td className="px-2 py-1.5 text-right text-blue-400">{put.greeks?.mid_iv ? `${(put.greeks.mid_iv * 100).toFixed(0)}%` : "—"}</td>
                    </>
                  ) : Array(6).fill(null).map((_, j) => (
                    <td key={j} className="px-2 py-1.5 text-gray-600 text-right">—</td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
