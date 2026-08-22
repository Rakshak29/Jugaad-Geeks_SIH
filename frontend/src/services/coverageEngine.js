// Evidence Band Logic
export const calculateEvidenceBand = (strength, recency) => {
  const score = strength * recency;
  if (score >= 0.8) return 'HIGH';
  if (score >= 0.5) return 'MODERATE';
  if (score >= 0.2) return 'LOW';
  return 'NONE';
};

const bandValue = {
  'HIGH': 3,
  'MODERATE': 2,
  'LOW': 1,
  'NONE': 0
};

export const getCoverageStatus = (before, after) => {
  const valB = bandValue[before] || 0;
  const valA = bandValue[after] || 0;
  
  if (valA === 0 && valB > 0) return 'Lost';
  if (valA < valB) return 'Degraded';
  return 'Maintained';
};

// Exact Optimizer (Lexicographic: min people -> min context switching)
export const findMinimumCoverageTeam = (gaps, availableEmployees, employeeCapabilitiesData) => {
  if (gaps.length === 0) return { team: [], residualGaps: [] };

  const candidates = availableEmployees.filter(emp => {
    return employeeCapabilitiesData.some(ec => 
      ec.employee_id === emp.employee_id && 
      gaps.includes(ec.capability_id) &&
      calculateEvidenceBand(ec.evidence_strength, ec.evidence_recency) !== 'NONE'
    );
  });

  const getSubsets = (arr) => {
    return arr.reduce(
      (subsets, value) => subsets.concat(subsets.map(set => [value, ...set])),
      [[]]
    );
  };

  const allTeams = getSubsets(candidates);
  
  let bestTeam = null;
  let bestCoveredCount = -1;
  let minSize = Infinity;
  let minContextPenalty = Infinity;

  allTeams.forEach(team => {
    if (team.length === 0) return;

    const coveredCaps = new Set();
    const teamIds = new Set(team.map(t => t.team_id));
    const contextPenalty = teamIds.size;

    team.forEach(emp => {
      const empCaps = employeeCapabilitiesData.filter(ec => 
        ec.employee_id === emp.employee_id && 
        gaps.includes(ec.capability_id) &&
        calculateEvidenceBand(ec.evidence_strength, ec.evidence_recency) !== 'NONE'
      );
      empCaps.forEach(ec => coveredCaps.add(ec.capability_id));
    });

    const coveredCount = coveredCaps.size;

    if (coveredCount > bestCoveredCount) {
      bestCoveredCount = coveredCount;
      minSize = team.length;
      minContextPenalty = contextPenalty;
      bestTeam = team;
    } else if (coveredCount === bestCoveredCount) {
      if (team.length < minSize) {
        minSize = team.length;
        minContextPenalty = contextPenalty;
        bestTeam = team;
      } else if (team.length === minSize) {
        if (contextPenalty < minContextPenalty) {
          minContextPenalty = contextPenalty;
          bestTeam = team;
        }
      }
    }
  });

  let residualGaps = [...gaps];
  const finalTeam = [];
  
  if (bestTeam) {
    const coveredByBest = new Set();
    bestTeam.forEach(emp => {
      const contributions = [];
      const empCaps = employeeCapabilitiesData.filter(ec => 
        ec.employee_id === emp.employee_id && 
        gaps.includes(ec.capability_id)
      );
      
      empCaps.forEach(ec => {
        const band = calculateEvidenceBand(ec.evidence_strength, ec.evidence_recency);
        if (band !== 'NONE') {
          coveredByBest.add(ec.capability_id);
          contributions.push({ capability_id: ec.capability_id, band });
        }
      });

      finalTeam.push({
        ...emp,
        contributions,
        rationale: `${emp.name} selected — ${contributions.map(c => `${c.band} evidence`).join(', ')}`
      });
    });

    residualGaps = gaps.filter(g => !coveredByBest.has(g));
  }

  return { team: finalTeam, residualGaps };
};
