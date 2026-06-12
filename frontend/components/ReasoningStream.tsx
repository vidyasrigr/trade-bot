"use client";

import { useState } from "react";
import ReactMarkdown from "react-markdown";
import { Brain, ChevronDown, ChevronUp } from "lucide-react";

interface Props {
  analystReports: {
    fundamental: string;
    technical: string;
    volatility: string;
    sentiment: string;
  };
  traderThesis: string;
  riskAssessment: string;
  isStreaming: boolean;
}

export function ReasoningStream({ analystReports, traderThesis, riskAssessment, isStreaming }: Props) {
  const [expanded, setExpanded] = useState<string | null>("trader");

  const analysts = [
    { key: "fundamental", label: "Fundamental Analyst", content: analystReports.fundamental, color: "text-blue-400" },
    { key: "technical",   label: "Technical Analyst",   content: analystReports.technical,   color: "text-purple-400" },
    { key: "volatility",  label: "Volatility Analyst",  content: analystReports.volatility,  color: "text-yellow-400" },
    { key: "sentiment",   label: "Sentiment Analyst",   content: analystReports.sentiment,   color: "text-pink-400" },
  ];

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
      <div className="px-4 py-3 border-b border-gray-800 flex items-center gap-2">
        <Brain className="w-4 h-4 text-green-400" />
        <span className="text-white font-semibold text-sm">Claude Reasoning</span>
        {isStreaming && <span className="text-green-400 text-xs animate-pulse ml-auto">● Live</span>}
      </div>

      <div className="divide-y divide-gray-800">
        {/* Analyst reports (collapsible) */}
        {analysts.map(({ key, label, content, color }) => (
          <ReasoningSection
            key={key}
            label={label}
            color={color}
            content={content}
            isExpanded={expanded === key}
            onToggle={() => setExpanded(prev => prev === key ? null : key)}
          />
        ))}

        {/* Main trader thesis (expanded by default) */}
        <ReasoningSection
          label="Trade Thesis"
          color="text-green-400"
          content={traderThesis}
          isExpanded={expanded === "trader"}
          onToggle={() => setExpanded(prev => prev === "trader" ? null : "trader")}
          primary
        />

        {/* Risk assessment */}
        {riskAssessment && (
          <ReasoningSection
            label="Risk Manager"
            color="text-orange-400"
            content={riskAssessment}
            isExpanded={expanded === "risk"}
            onToggle={() => setExpanded(prev => prev === "risk" ? null : "risk")}
          />
        )}
      </div>
    </div>
  );
}

function ReasoningSection({
  label, color, content, isExpanded, onToggle, primary = false,
}: {
  label: string;
  color: string;
  content: string;
  isExpanded: boolean;
  onToggle: () => void;
  primary?: boolean;
}) {
  if (!content && !primary) return null;

  return (
    <div>
      <button
        onClick={onToggle}
        className="w-full flex items-center justify-between px-4 py-2.5 hover:bg-gray-800/40 transition"
      >
        <span className={`text-xs font-semibold ${color}`}>{label}</span>
        {isExpanded ? (
          <ChevronUp className="w-3 h-3 text-gray-500" />
        ) : (
          <ChevronDown className="w-3 h-3 text-gray-500" />
        )}
      </button>
      {isExpanded && (
        <div className="px-4 pb-3">
          {content ? (
            <div className="text-gray-300 text-xs leading-relaxed prose prose-invert prose-xs max-w-none">
              <ReactMarkdown>{content}</ReactMarkdown>
            </div>
          ) : (
            <div className="text-gray-600 text-xs italic">Waiting for analysis...</div>
          )}
        </div>
      )}
    </div>
  );
}
