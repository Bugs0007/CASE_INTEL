"use client";

import { useState } from "react";
import { Search, ArrowLeft } from "lucide-react";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Spotlight } from "./spotlight";
import { mockSearchResults } from "../mock-data";

interface SearchSceneProps {
  highlight: string;
  sceneState?: string;
}

export function SearchScene({ highlight, sceneState }: SearchSceneProps) {
  const showResults = sceneState === "results";
  // Local-only: ticking a row here never leaves this component, let alone
  // the browser -- there is no submit handler and nothing to send.
  const [selected, setSelected] = useState<Set<string>>(
    () => new Set(mockSearchResults.slice(0, 2).map((r) => r.cnr)),
  );

  function toggle(cnr: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(cnr)) next.delete(cnr);
      else next.add(cnr);
      return next;
    });
  }

  return (
    <div className="max-w-[900px] mx-auto pb-4">
      <div className="mb-5">
        <span className="inline-flex items-center gap-1.5 text-sm text-gray-600">
          <ArrowLeft className="h-4 w-4" />
          Back to Cases
        </span>
        <h1 className="text-page-title text-gray-900 mt-2 mb-1.5">Search by Advocate</h1>
        <p className="text-sm text-gray-600">
          Pick a state and enter your advocate name or bar registration number. Case Intel
          searches district courts and gathers all your cases — then you choose which to add.
        </p>
      </div>

      <Spotlight id="search-form" active={highlight} className="block mb-6">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Search className="h-5 w-5 text-gray-500" />
              District Courts
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">State</label>
              <select className="ci-select" disabled value="TG">
                <option value="TG">Telangana</option>
              </select>
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">
                District <span className="font-normal text-gray-400">(optional)</span>
              </label>
              <select className="ci-select" disabled value="">
                <option value="">All districts (thorough, several minutes)</option>
              </select>
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">
                Advocate Name or Bar Code
              </label>
              <input className="ci-input" disabled value="Meera Reddy" readOnly />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">Case Status</label>
              <div className="flex gap-4 text-sm text-gray-600">
                <span className="flex items-center gap-1.5">
                  <input type="radio" checked readOnly /> Both
                </span>
                <span className="flex items-center gap-1.5">
                  <input type="radio" disabled /> Pending
                </span>
                <span className="flex items-center gap-1.5">
                  <input type="radio" disabled /> Disposed
                </span>
              </div>
            </div>
            <Button className="w-full" tabIndex={-1}>
              <Search className="h-4 w-4" />
              {showResults ? "Search State-wide" : "Search This District"}
            </Button>
          </CardContent>
        </Card>
      </Spotlight>

      {showResults && (
        <Spotlight id="results" active={highlight} className="block">
          <Card>
            <CardHeader>
              <CardTitle>{mockSearchResults.length} Case(s) Found</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="overflow-auto rounded-lg border border-gray-100 mb-4">
                <table className="w-full text-sm">
                  <thead className="bg-gray-50 text-left text-xs text-gray-500">
                    <tr>
                      <th className="px-3 py-2 w-8"></th>
                      <th className="px-3 py-2 font-medium">Case Number</th>
                      <th className="px-3 py-2 font-medium">Parties</th>
                      <th className="px-3 py-2 font-medium hidden sm:table-cell">Court</th>
                      <th className="px-3 py-2 font-medium">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {mockSearchResults.map((r) => (
                      <tr key={r.cnr}>
                        <td className="px-3 py-2">
                          <input
                            type="checkbox"
                            checked={selected.has(r.cnr)}
                            onChange={() => toggle(r.cnr)}
                          />
                        </td>
                        <td className="px-3 py-2 font-mono whitespace-nowrap">{r.caseNumber}</td>
                        <td className="px-3 py-2 text-gray-700">
                          {r.petitioner} vs {r.respondent}
                        </td>
                        <td className="px-3 py-2 text-gray-600 hidden sm:table-cell">{r.court}</td>
                        <td className="px-3 py-2 text-gray-600">{r.status}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <Button tabIndex={-1}>Add {selected.size || ""} to My Cases</Button>
            </CardContent>
          </Card>
        </Spotlight>
      )}
    </div>
  );
}
