import { useMemo, useState } from 'react'
import { modelDefinitions } from '@/data/modelDefinitions'
import { createScenarioDefaults, scenarioNames } from '@/valuation/scenarios'
import { evaluateModels, modelEligibility } from '@/valuation/modelSelector'
import { combineValuations } from '@/valuation/weighting'

export default function useValuation(company) {
  const defaults = useMemo(() => createScenarioDefaults(company), [company])
  const [assumptions, setAssumptions] = useState(() =>
    createScenarioDefaults(company),
  )
  const [activeScenario, setActiveScenario] = useState('base')
  const [enabled, setEnabled] = useState(() =>
    Object.fromEntries(
      modelDefinitions.map((model) => [
        model.id,
        model.defaultEnabled &&
          modelEligibility(model, company).status === 'applicable',
      ]),
    ),
  )
  const [weights, setWeights] = useState(() =>
    Object.fromEntries(
      modelDefinitions.map((model) => [model.id, model.defaultWeight]),
    ),
  )
  const scenarios = useMemo(
    () =>
      Object.fromEntries(
        scenarioNames.map((name) => {
          const results = evaluateModels(company, assumptions[name])
          return [
            name,
            {
              results,
              summary: combineValuations(
                results,
                enabled,
                weights,
                company.price,
              ),
            },
          ]
        }),
      ),
    [company, assumptions, enabled, weights],
  )
  function editAssumption(key, value) {
    setAssumptions((previous) => ({
      ...previous,
      [activeScenario]: { ...previous[activeScenario], [key]: value },
    }))
  }
  function resetAssumptions() {
    setAssumptions((previous) => ({
      ...previous,
      [activeScenario]: { ...defaults[activeScenario] },
    }))
  }
  function resetWeights() {
    setWeights(
      Object.fromEntries(
        modelDefinitions.map((model) => [model.id, model.defaultWeight]),
      ),
    )
    setEnabled(
      Object.fromEntries(
        modelDefinitions.map((model) => [
          model.id,
          model.defaultEnabled &&
            modelEligibility(model, company).status === 'applicable',
        ]),
      ),
    )
  }
  return {
    defaults,
    assumptions,
    activeScenario,
    setActiveScenario,
    enabled,
    setEnabled,
    weights,
    setWeights,
    scenarios,
    editAssumption,
    resetAssumptions,
    resetWeights,
    ...scenarios[activeScenario],
  }
}
