//STEP 1. Merge same type relations:
// Batched: one start node at a time, committed every 10000 start nodes. The single-transaction form grouped ALL
// relations at once and exceeded dbms.memory.transaction.total.max.
CALL apoc.periodic.iterate(
  // 1. DRIVING STATEMENT
  "MATCH (a) WHERE count{(a)-->()} > 1 RETURN a",
  
  // 2. ACTION STATEMENT
  "MATCH (a)-[r]->(b)
   WHERE NOT type(r) IN ['is_a', 'part_of', 'MemberOf', 'derivative_of']
   WITH a, b, type(r) AS relType, collect(r) AS rels
   WHERE size(rels) > 1
   
   UNWIND rels AS r
   WITH a, b, relType, r
   ORDER BY coalesce(r.RelationNumberOfReferences, 0) DESC
   WITH a, b, relType, collect(r) AS sortedRels
   
   CALL apoc.refactor.mergeRelationships(sortedRels, {properties: 'combine'})
   YIELD rel
   
   WITH rel, properties(rel) AS props
   WITH rel, apoc.map.fromLists(
       keys(props),
       [k IN keys(props) |
           apoc.coll.toSet([v IN apoc.coll.flatten([props[k]]) WHERE v IS NOT NULL])
       ]
   ) AS uniqueMap
   
   WITH rel, apoc.map.fromLists(
       keys(uniqueMap),
       [k IN keys(uniqueMap) |
           CASE size(uniqueMap[k])
               WHEN 0 THEN null
               WHEN 1 THEN uniqueMap[k][0]
               ELSE uniqueMap[k]
           END
       ]
   ) AS finalProps
   
   SET rel = finalProps",
   
  // 3. CONFIGURATION
  {
    batchSize: 10000, 
    parallel: true, 
    retries: 3,
    concurrency: 4 
  }
)
// 4. CAPTURE AND FORMAT THE OUTPUT
YIELD committedOperations, failedOperations, errorMessages
RETURN 
  "Same reltype" AS merge_type,
  committedOperations AS mergedCount,
  failedOperations AS failedCount,
  errorMessages AS errors

UNION

//STEP 2. Merge FunctionalAssociation into Regulation:
//ESTIMATE: CALL { {DRIVING} } WITH anchor WHERE rand() < $p WITH collect(anchor) AS sample UNWIND sample AS anchor WITH sample, startNode(anchor) AS a, endNode(anchor) AS b MATCH (a)-[e:`FunctionalAssociation`]->(b) RETURN size(sample) AS sampleN, count(e) AS merges
// apoc.periodic.iterate: batches of 10000, committed separately; progress is reported by the App.
CALL apoc.periodic.iterate(
  // 1. DRIVING STATEMENT
  "MATCH (a)-[anchor:`Regulation`]->(b) WHERE EXISTS { MATCH (a)-[:`FunctionalAssociation`]->(b) } RETURN anchor",

  // 2. ACTION STATEMENT
  "WITH anchor, startNode(anchor) AS a, endNode(anchor) AS b
   MATCH (a)-[evidence:`FunctionalAssociation`]->(b)
   WITH anchor, collect(evidence) AS evidenceRels
   CALL apoc.refactor.mergeRelationships([anchor] + evidenceRels, {properties: 'combine', produceSelfRel: false})
   YIELD rel
   WITH rel, properties(rel) AS props
   WITH rel, apoc.map.fromLists(
       keys(props),
       [k IN keys(props) |
           apoc.coll.toSet([x IN apoc.coll.flatten([props[k]]) WHERE x IS NOT NULL])
       ]
   ) AS uniqueMap
   WITH rel, apoc.map.fromLists(
       keys(uniqueMap),
       [k IN keys(uniqueMap) |
           CASE size(uniqueMap[k])
               WHEN 0 THEN null
               WHEN 1 THEN uniqueMap[k][0]
               ELSE uniqueMap[k]
           END
       ]
   ) AS finalProps
   SET rel = finalProps",

  // 3. CONFIGURATION
  {
    batchSize: 10000,
    parallel: true,
    retries: 3,
    concurrency: 4
  }
)
YIELD committedOperations, failedOperations, errorMessages
RETURN
  "FuncAssoc2Regulation" AS merge_type,
  committedOperations AS mergedCount,
  failedOperations AS failedCount,
  errorMessages AS errors

UNION

//STEP 3. Merge reversed FunctionalAssociation into Regulation:
//ESTIMATE: CALL { {DRIVING} } WITH anchor WHERE rand() < $p WITH collect(anchor) AS sample UNWIND sample AS anchor WITH sample, startNode(anchor) AS a, endNode(anchor) AS b MATCH (b)-[e:`FunctionalAssociation`]->(a) RETURN size(sample) AS sampleN, count(e) AS merges
// apoc.periodic.iterate: batches of 10000, committed separately; progress is reported by the App.
CALL apoc.periodic.iterate(
  // 1. DRIVING STATEMENT
  "MATCH (a)-[anchor:`Regulation`]->(b) WHERE EXISTS { MATCH (b)-[e:`FunctionalAssociation`]->(a) } RETURN anchor",

  // 2. ACTION STATEMENT
  "WITH anchor, startNode(anchor) AS a, endNode(anchor) AS b
   MATCH (b)-[assoc:`FunctionalAssociation`]->(a)
   WITH anchor, collect(assoc) AS evidence
   WITH anchor, evidence, [rb IN evidence | properties(rb)] AS assoc_props_list
   WITH anchor, evidence, assoc_props_list,
        apoc.coll.toSet(keys(properties(anchor)) + apoc.coll.flatten([m IN assoc_props_list | keys(m)])) AS all_keys
   WITH anchor, evidence,
        apoc.map.fromLists(all_keys, [k IN all_keys |
            apoc.coll.flatten([coalesce(properties(anchor)[k], [])]) +
            apoc.coll.flatten([m IN assoc_props_list | coalesce(m[k], [])])
        ]) AS mergedProps
   SET anchor = mergedProps
   WITH anchor, evidence
   UNWIND evidence AS rb
   DELETE rb",

  // 3. CONFIGURATION
  {
    batchSize: 10000,
    parallel: true,
    retries: 3,
    concurrency: 4
  }
)
YIELD committedOperations, failedOperations, errorMessages
RETURN
  "reversedFuncAssoc2Regulation" AS merge_type,
  committedOperations AS mergedCount,
  failedOperations AS failedCount,
  errorMessages AS errors

UNION

//STEP 4. Create DirectRegulation from Binding + Regulation:
//ESTIMATE: CALL { {DRIVING} } WITH a WHERE rand() < $p WITH collect(a) AS sample UNWIND sample AS a MATCH (a)-[r:`Regulation`|`Binding`]->(b) WHERE r.RelationNumberOfReferences > 1 WITH sample, a, b, count(r) AS c WHERE c > 1 RETURN size(sample) AS sampleN, sum(c - 1) AS merges
// apoc.periodic.iterate: batches of 10000, committed separately; progress is reported by the App.
CALL apoc.periodic.iterate(
  // 1. DRIVING STATEMENT
  "MATCH (a) WHERE count{ (a)-[r:`Regulation`|`Binding`]->() WHERE r.RelationNumberOfReferences > 1 } > 1 RETURN a",

  // 2. ACTION STATEMENT
  "MATCH (a)-[r:`Regulation`|`Binding`]->(b)
   WHERE r.RelationNumberOfReferences > 1
   WITH a, b, collect(r) AS rels
   WHERE size(rels) > 1
   UNWIND rels AS r
   WITH a, b, r
   ORDER BY coalesce(r.RelationNumberOfReferences, 0) DESC
   WITH a, b, collect(r) AS sortedRels
   WITH a, b, sortedRels, properties(sortedRels[0]) AS baseProps
   CREATE (a)-[newRel:DirectRegulation]->(b)
   SET newRel = baseProps
   WITH newRel, sortedRels
   CALL apoc.refactor.mergeRelationships([newRel] + sortedRels, {properties: 'combine', produceSelfRel: false})
   YIELD rel
   WITH rel, properties(rel) AS props
   WITH rel, apoc.map.fromLists(
       keys(props),
       [k IN keys(props) |
           apoc.coll.toSet([x IN apoc.coll.flatten([props[k]]) WHERE x IS NOT NULL])
       ]
   ) AS uniqueMap
   WITH rel, apoc.map.fromLists(
       keys(uniqueMap),
       [k IN keys(uniqueMap) |
           CASE size(uniqueMap[k])
               WHEN 0 THEN null
               WHEN 1 THEN uniqueMap[k][0]
               ELSE uniqueMap[k]
           END
       ]
   ) AS finalProps
   SET rel = finalProps",

  // 3. CONFIGURATION
  {
    batchSize: 10000,
    parallel: true,
    retries: 3,
    concurrency: 4
  }
)
YIELD committedOperations, failedOperations, errorMessages
RETURN
  "createDirectRegulation" AS merge_type,
  committedOperations AS mergedCount,
  failedOperations AS failedCount,
  errorMessages AS errors

UNION

//STEP 5. Create DirectRegulation from reversed Binding + Regulation:
//ESTIMATE: CALL { {DRIVING} } WITH a, b WHERE rand() < $p WITH collect([a, b]) AS sample UNWIND sample AS ab WITH sample, ab[0] AS a, ab[1] AS b MATCH (a)-[reg:Regulation]->(b) WITH sample, a, b, count(reg) AS regs MATCH (b)-[bind:Binding]->(a) WHERE bind.RelationNumberOfReferences > 2 WITH sample, a, b, regs, count(bind) AS binds RETURN size(sample) AS sampleN, sum(regs + binds - 1) AS merges
// apoc.periodic.iterate: batches of 10000, committed separately; progress is reported by the App.
CALL apoc.periodic.iterate(
  // 1. DRIVING STATEMENT
  "MATCH (a)-[:Regulation]->(b) WHERE EXISTS { MATCH (b)-[bd:Binding]->(a) WHERE bd.RelationNumberOfReferences > 2 } RETURN DISTINCT a, b",

  // 2. ACTION STATEMENT
  "MATCH (a)-[reg:Regulation]->(b)
   MATCH (b)-[bind:Binding]->(a)
   WHERE bind.RelationNumberOfReferences > 2
   WITH a, b, collect(DISTINCT reg) AS regs, collect(DISTINCT bind) AS rev_binds
   WITH a, b, regs, rev_binds,
        [r IN regs + rev_binds | properties(r)] AS all_props_maps
   WITH a, b, regs, rev_binds, all_props_maps,
        apoc.coll.toSet(apoc.coll.flatten([m IN all_props_maps | keys(m)])) AS all_keys
   WITH a, b, regs, rev_binds,
        apoc.map.fromLists(all_keys, [k IN all_keys |
           apoc.coll.flatten([m IN all_props_maps | coalesce(m[k], [])])
        ]) AS combinedProps
   CREATE (a)-[newRel:DirectRegulation]->(b)
   SET newRel = combinedProps
   WITH regs, rev_binds, newRel
   FOREACH (r IN regs | DELETE r)
   FOREACH (rb IN rev_binds | DELETE rb)
   WITH newRel, properties(newRel) AS props
   WITH newRel, apoc.map.fromLists(
       keys(props),
       [k IN keys(props) |
           apoc.coll.toSet([x IN apoc.coll.flatten([props[k]]) WHERE x IS NOT NULL])
       ]
   ) AS uniqueMap
   WITH newRel, apoc.map.fromLists(
       keys(uniqueMap),
       [k IN keys(uniqueMap) |
           CASE size(uniqueMap[k])
               WHEN 0 THEN null
               WHEN 1 THEN uniqueMap[k][0]
               ELSE uniqueMap[k]
           END
       ]
   ) AS finalProps
   SET newRel = finalProps",

  // 3. CONFIGURATION
  {
    batchSize: 10000,
    parallel: true,
    retries: 3,
    concurrency: 4
  }
)
YIELD committedOperations, failedOperations, errorMessages
RETURN
  "createDirectRegulationReversedBinding" AS merge_type,
  committedOperations AS mergedCount,
  failedOperations AS failedCount,
  errorMessages AS errors

UNION

//STEP 6. Merge new DirectRegulation:
//ESTIMATE: CALL { {DRIVING} } WITH a WHERE rand() < $p WITH collect(a) AS sample UNWIND sample AS a MATCH (a)-[r:`DirectRegulation`]->(b) WITH sample, a, b, count(r) AS c WHERE c > 1 RETURN size(sample) AS sampleN, sum(c - 1) AS merges
// apoc.periodic.iterate: batches of 10000, committed separately; progress is reported by the App.
CALL apoc.periodic.iterate(
  // 1. DRIVING STATEMENT
  "MATCH (a) WHERE count{(a)-[:`DirectRegulation`]->()} > 1 RETURN a",

  // 2. ACTION STATEMENT
  "MATCH (a)-[r:`DirectRegulation`]->(b)
   WITH a, b, collect(r) AS rels
   WHERE size(rels) > 1
   UNWIND rels AS r
   WITH a, b, r
   ORDER BY coalesce(r.RelationNumberOfReferences, 0) DESC
   WITH a, b, collect(r) AS sortedRels
   CALL apoc.refactor.mergeRelationships(sortedRels, {properties: 'combine'})
   YIELD rel
   WITH rel, properties(rel) AS props
   WITH rel, apoc.map.fromLists(
       keys(props),
       [k IN keys(props) |
           apoc.coll.toSet([x IN apoc.coll.flatten([props[k]]) WHERE x IS NOT NULL])
       ]
   ) AS uniqueMap
   WITH rel, apoc.map.fromLists(
       keys(uniqueMap),
       [k IN keys(uniqueMap) |
           CASE size(uniqueMap[k])
               WHEN 0 THEN null
               WHEN 1 THEN uniqueMap[k][0]
               ELSE uniqueMap[k]
           END
       ]
   ) AS finalProps
   SET rel = finalProps",

  // 3. CONFIGURATION
  {
    batchSize: 10000,
    parallel: true,
    retries: 3,
    concurrency: 4
  }
)
YIELD committedOperations, failedOperations, errorMessages
RETURN
  "Same reltype after DirectRegulation" AS merge_type,
  committedOperations AS mergedCount,
  failedOperations AS failedCount,
  errorMessages AS errors

UNION

//STEP 7. Convert ProtModification to Regulation for non-enzymes:
// parallel: false because every row creates and deletes a relationship, and parallel batches deadlocked on shared nodes.
// apoc.periodic.iterate: batches of 10000, committed separately; progress is reported by the App.
CALL apoc.periodic.iterate(
  // 1. DRIVING STATEMENT
  "MATCH (p) WHERE p.Name IN ['protein kinase', 'acetyltransferase', 'peptide hydrolase', 'deacetylase', 'protein methyltransferase', 'histone modification enzyme', 'aminoacyltransferase', 'peptide synthase', 'protein phosphatase'] OPTIONAL MATCH (child)-[:is_a*]->(p) WITH collect(DISTINCT child) + collect(DISTINCT p) AS enzymeNodes MATCH (n)-[r:ProtModification]->(t) WHERE NOT n IN enzymeNodes RETURN r",

  // 2. ACTION STATEMENT
  "WITH r, startNode(r) AS n, endNode(r) AS t, properties(r) AS oldProps
   CREATE (n)-[newRel:Regulation]->(t)
   SET newRel = oldProps
   DELETE r",

  // 3. CONFIGURATION
  {
    batchSize: 10000,
    parallel: false,
    retries: 3
  }
)
YIELD committedOperations, failedOperations, errorMessages
RETURN
  "ConvertProtMod2Regulation" AS merge_type,
  committedOperations AS mergedCount,
  failedOperations AS failedCount,
  errorMessages AS errors

UNION

//STEP 8. Merge Regulation into ProtModification for enzymes:
//ESTIMATE: CALL { {DRIVING} } WITH enzyme WHERE rand() < $p WITH collect(enzyme) AS sample UNWIND sample AS enzyme MATCH (enzyme)-[r1:ProtModification]->(b) MATCH (enzyme)-[r2:Regulation]->(b) WITH sample, enzyme, b, count(DISTINCT r1) + count(DISTINCT r2) AS c RETURN size(sample) AS sampleN, sum(c - 1) AS merges
// apoc.periodic.iterate: batches of 10000, committed separately; progress is reported by the App.
CALL apoc.periodic.iterate(
  // 1. DRIVING STATEMENT
  "MATCH (p) WHERE p.Name IN ['protein kinase', 'acetyltransferase', 'peptide hydrolase', 'deacetylase', 'protein methyltransferase', 'histone modification enzyme', 'aminoacyltransferase', 'peptide synthase', 'protein phosphatase'] OPTIONAL MATCH (child)-[:is_a*]->(p) WITH collect(DISTINCT p) + collect(DISTINCT child) AS all_enzymes UNWIND all_enzymes AS enzyme WITH DISTINCT enzyme WHERE EXISTS { MATCH (enzyme)-[:ProtModification]->()<-[:Regulation]-(enzyme) } RETURN enzyme",

  // 2. ACTION STATEMENT
  "MATCH (enzyme)-[r1:ProtModification]->(b)
   MATCH (enzyme)-[r2:Regulation]->(b)
   WITH enzyme, b, collect(DISTINCT r1) + collect(DISTINCT r2) AS rels
   UNWIND rels AS r
   WITH enzyme, b, r
   ORDER BY
     CASE type(r)
       WHEN 'ProtModification' THEN 1
       WHEN 'Regulation' THEN 2
     END ASC,
     coalesce(r.RelationNumberOfReferences, 0) DESC
   WITH enzyme, b, collect(r) AS sortedRels
   CALL apoc.refactor.mergeRelationships(sortedRels, {properties: 'combine'})
   YIELD rel
   WITH rel, properties(rel) AS props
   WITH rel, apoc.map.fromLists(
       keys(props),
       [k IN keys(props) |
           apoc.coll.toSet([x IN apoc.coll.flatten([props[k]]) WHERE x IS NOT NULL])
       ]
   ) AS uniqueMap
   WITH rel, apoc.map.fromLists(
       keys(uniqueMap),
       [k IN keys(uniqueMap) |
           CASE size(uniqueMap[k])
               WHEN 0 THEN null
               WHEN 1 THEN uniqueMap[k][0]
               ELSE uniqueMap[k]
           END
       ]
   ) AS finalProps
   SET rel = finalProps",

  // 3. CONFIGURATION
  {
    batchSize: 10000,
    parallel: true,
    retries: 3,
    concurrency: 4
  }
)
YIELD committedOperations, failedOperations, errorMessages
RETURN
  "Regulation2ProtMod" AS merge_type,
  committedOperations AS mergedCount,
  failedOperations AS failedCount,
  errorMessages AS errors

UNION

//STEP 9. Merge Regulation|Binding|ProtModification into DirectRegulation:
//ESTIMATE: CALL { {DRIVING} } WITH anchor WHERE rand() < $p WITH collect(anchor) AS sample UNWIND sample AS anchor WITH sample, startNode(anchor) AS a, endNode(anchor) AS b MATCH (a)-[e:`Regulation`|`Binding`|`ProtModification`]->(b) RETURN size(sample) AS sampleN, count(e) AS merges
// apoc.periodic.iterate: batches of 10000, committed separately; progress is reported by the App.
CALL apoc.periodic.iterate(
  // 1. DRIVING STATEMENT
  "MATCH (a)-[anchor:`DirectRegulation`]->(b) WHERE EXISTS { MATCH (a)-[:`Regulation`|`Binding`|`ProtModification`]->(b) } RETURN anchor",

  // 2. ACTION STATEMENT
  "WITH anchor, startNode(anchor) AS a, endNode(anchor) AS b
   MATCH (a)-[evidence:`Regulation`|`Binding`|`ProtModification`]->(b)
   WITH anchor, collect(evidence) AS evidenceRels
   CALL apoc.refactor.mergeRelationships([anchor] + evidenceRels, {properties: 'combine', produceSelfRel: false})
   YIELD rel
   WITH rel, properties(rel) AS props
   WITH rel, apoc.map.fromLists(
       keys(props),
       [k IN keys(props) |
           apoc.coll.toSet([x IN apoc.coll.flatten([props[k]]) WHERE x IS NOT NULL])
       ]
   ) AS uniqueMap
   WITH rel, apoc.map.fromLists(
       keys(uniqueMap),
       [k IN keys(uniqueMap) |
           CASE size(uniqueMap[k])
               WHEN 0 THEN null
               WHEN 1 THEN uniqueMap[k][0]
               ELSE uniqueMap[k]
           END
       ]
   ) AS finalProps
   SET rel = finalProps",

  // 3. CONFIGURATION
  {
    batchSize: 10000,
    parallel: true,
    retries: 3,
    concurrency: 4
  }
)
YIELD committedOperations, failedOperations, errorMessages
RETURN
  "RegProtModBind2DirectRegulation" AS merge_type,
  committedOperations AS mergedCount,
  failedOperations AS failedCount,
  errorMessages AS errors

UNION

//STEP 10. Merge reversed Binding to DirectRegulation:
//ESTIMATE: CALL { {DRIVING} } WITH anchor WHERE rand() < $p WITH collect(anchor) AS sample UNWIND sample AS anchor WITH sample, startNode(anchor) AS a, endNode(anchor) AS b MATCH (b)-[e:`Binding`]->(a) WHERE e.RelationNumberOfReferences > 2 RETURN size(sample) AS sampleN, count(e) AS merges
// apoc.periodic.iterate: batches of 10000, committed separately; progress is reported by the App.
CALL apoc.periodic.iterate(
  // 1. DRIVING STATEMENT
  "MATCH (a)-[anchor:`DirectRegulation`]->(b) WHERE EXISTS { MATCH (b)-[e:`Binding`]->(a) WHERE e.RelationNumberOfReferences > 2 } RETURN anchor",

  // 2. ACTION STATEMENT
  "WITH anchor, startNode(anchor) AS a, endNode(anchor) AS b
   MATCH (b)-[assoc:`Binding`]->(a)
   WHERE assoc.RelationNumberOfReferences > 2
   WITH anchor, collect(assoc) AS evidence
   WITH anchor, evidence, [rb IN evidence | properties(rb)] AS assoc_props_list
   WITH anchor, evidence, assoc_props_list,
        apoc.coll.toSet(keys(properties(anchor)) + apoc.coll.flatten([m IN assoc_props_list | keys(m)])) AS all_keys
   WITH anchor, evidence,
        apoc.map.fromLists(all_keys, [k IN all_keys |
            apoc.coll.flatten([coalesce(properties(anchor)[k], [])]) +
            apoc.coll.flatten([m IN assoc_props_list | coalesce(m[k], [])])
        ]) AS mergedProps
   SET anchor = mergedProps
   WITH anchor, evidence
   UNWIND evidence AS rb
   DELETE rb",

  // 3. CONFIGURATION
  {
    batchSize: 10000,
    parallel: true,
    retries: 3,
    concurrency: 4
  }
)
YIELD committedOperations, failedOperations, errorMessages
RETURN
  "reversedBind2DirectRegulation" AS merge_type,
  committedOperations AS mergedCount,
  failedOperations AS failedCount,
  errorMessages AS errors

UNION

//STEP 11. Merge Regulation|FunctionalAssociation to Expression:
//ESTIMATE: CALL { {DRIVING} } WITH anchor WHERE rand() < $p WITH collect(anchor) AS sample UNWIND sample AS anchor WITH sample, startNode(anchor) AS a, endNode(anchor) AS b MATCH (a)-[e:`Regulation`|`FunctionalAssociation`]->(b) RETURN size(sample) AS sampleN, count(e) AS merges
// apoc.periodic.iterate: batches of 10000, committed separately; progress is reported by the App.
CALL apoc.periodic.iterate(
  // 1. DRIVING STATEMENT
  "MATCH (a)-[anchor:`Expression`]->(b) WHERE EXISTS { MATCH (a)-[:`Regulation`|`FunctionalAssociation`]->(b) } RETURN anchor",

  // 2. ACTION STATEMENT
  "WITH anchor, startNode(anchor) AS a, endNode(anchor) AS b
   MATCH (a)-[evidence:`Regulation`|`FunctionalAssociation`]->(b)
   WITH anchor, collect(evidence) AS evidenceRels
   CALL apoc.refactor.mergeRelationships([anchor] + evidenceRels, {properties: 'combine', produceSelfRel: false})
   YIELD rel
   WITH rel, properties(rel) AS props
   WITH rel, apoc.map.fromLists(
       keys(props),
       [k IN keys(props) |
           apoc.coll.toSet([x IN apoc.coll.flatten([props[k]]) WHERE x IS NOT NULL])
       ]
   ) AS uniqueMap
   WITH rel, apoc.map.fromLists(
       keys(uniqueMap),
       [k IN keys(uniqueMap) |
           CASE size(uniqueMap[k])
               WHEN 0 THEN null
               WHEN 1 THEN uniqueMap[k][0]
               ELSE uniqueMap[k]
           END
       ]
   ) AS finalProps
   SET rel = finalProps",

  // 3. CONFIGURATION
  {
    batchSize: 10000,
    parallel: true,
    retries: 3,
    concurrency: 4
  }
)
YIELD committedOperations, failedOperations, errorMessages
RETURN
  "RegFuncAssoc2Expression" AS merge_type,
  committedOperations AS mergedCount,
  failedOperations AS failedCount,
  errorMessages AS errors

UNION

//STEP 12. Merge reversed FunctionalAssociation into Expression
//ESTIMATE: CALL { {DRIVING} } WITH anchor WHERE rand() < $p WITH collect(anchor) AS sample UNWIND sample AS anchor WITH sample, startNode(anchor) AS a, endNode(anchor) AS b MATCH (b)-[e:`FunctionalAssociation`]->(a) RETURN size(sample) AS sampleN, count(e) AS merges
// apoc.periodic.iterate: batches of 10000, committed separately; progress is reported by the App.
CALL apoc.periodic.iterate(
  // 1. DRIVING STATEMENT
  "MATCH (a)-[anchor:`Expression`]->(b) WHERE EXISTS { MATCH (b)-[e:`FunctionalAssociation`]->(a) } RETURN anchor",

  // 2. ACTION STATEMENT
  "WITH anchor, startNode(anchor) AS a, endNode(anchor) AS b
   MATCH (b)-[assoc:`FunctionalAssociation`]->(a)
   WITH anchor, collect(assoc) AS evidence
   WITH anchor, evidence, [rb IN evidence | properties(rb)] AS assoc_props_list
   WITH anchor, evidence, assoc_props_list,
        apoc.coll.toSet(keys(properties(anchor)) + apoc.coll.flatten([m IN assoc_props_list | keys(m)])) AS all_keys
   WITH anchor, evidence,
        apoc.map.fromLists(all_keys, [k IN all_keys |
            apoc.coll.flatten([coalesce(properties(anchor)[k], [])]) +
            apoc.coll.flatten([m IN assoc_props_list | coalesce(m[k], [])])
        ]) AS mergedProps
   SET anchor = mergedProps
   WITH anchor, evidence
   UNWIND evidence AS rb
   DELETE rb",

  // 3. CONFIGURATION
  {
    batchSize: 10000,
    parallel: true,
    retries: 3,
    concurrency: 4
  }
)
YIELD committedOperations, failedOperations, errorMessages
RETURN
  "reversedFuncAssoc2Expression" AS merge_type,
  committedOperations AS mergedCount,
  failedOperations AS failedCount,
  errorMessages AS errors

UNION

//STEP 13. Merge Regulation|Expression to PromoterBinding:
//ESTIMATE: CALL { {DRIVING} } WITH anchor WHERE rand() < $p WITH collect(anchor) AS sample UNWIND sample AS anchor WITH sample, startNode(anchor) AS a, endNode(anchor) AS b MATCH (a)-[e:`Regulation`|`Expression`]->(b) RETURN size(sample) AS sampleN, count(e) AS merges
// apoc.periodic.iterate: batches of 10000, committed separately; progress is reported by the App.
CALL apoc.periodic.iterate(
  // 1. DRIVING STATEMENT
  "MATCH (a)-[anchor:`PromoterBinding`]->(b) WHERE EXISTS { MATCH (a)-[:`Regulation`|`Expression`]->(b) } RETURN anchor",

  // 2. ACTION STATEMENT
  "WITH anchor, startNode(anchor) AS a, endNode(anchor) AS b
   MATCH (a)-[evidence:`Regulation`|`Expression`]->(b)
   WITH anchor, collect(evidence) AS evidenceRels
   CALL apoc.refactor.mergeRelationships([anchor] + evidenceRels, {properties: 'combine', produceSelfRel: false})
   YIELD rel
   RETURN count(rel) AS merged",

  // 3. CONFIGURATION
  {
    batchSize: 10000,
    parallel: true,
    retries: 3,
    concurrency: 4
  }
)
YIELD committedOperations, failedOperations, errorMessages
RETURN
  "RegExpr2PromoterBinding" AS merge_type,
  committedOperations AS mergedCount,
  failedOperations AS failedCount,
  errorMessages AS errors

UNION

//STEP 14. Merge FunctionalAssociation into QuantitativeChange:
//ESTIMATE: CALL { {DRIVING} } WITH anchor WHERE rand() < $p WITH collect(anchor) AS sample UNWIND sample AS anchor WITH sample, startNode(anchor) AS a, endNode(anchor) AS b MATCH (a)-[e:`FunctionalAssociation`]->(b) RETURN size(sample) AS sampleN, count(e) AS merges
// apoc.periodic.iterate: batches of 10000, committed separately; progress is reported by the App.
CALL apoc.periodic.iterate(
  // 1. DRIVING STATEMENT
  "MATCH (a)-[anchor:`QuantitativeChange`]->(b) WHERE EXISTS { MATCH (a)-[:`FunctionalAssociation`]->(b) } RETURN anchor",

  // 2. ACTION STATEMENT
  "WITH anchor, startNode(anchor) AS a, endNode(anchor) AS b
   MATCH (a)-[evidence:`FunctionalAssociation`]->(b)
   WITH anchor, collect(evidence) AS evidenceRels
   CALL apoc.refactor.mergeRelationships([anchor] + evidenceRels, {properties: 'combine', produceSelfRel: false})
   YIELD rel
   RETURN count(rel) AS merged",

  // 3. CONFIGURATION
  {
    batchSize: 10000,
    parallel: true,
    retries: 3,
    concurrency: 4
  }
)
YIELD committedOperations, failedOperations, errorMessages
RETURN
  "FuncAssoc2QuantitativeChange" AS merge_type,
  committedOperations AS mergedCount,
  failedOperations AS failedCount,
  errorMessages AS errors

UNION

//STEP 15. Merge reversed FunctionalAssociation into QuantitativeChange
//ESTIMATE: CALL { {DRIVING} } WITH anchor WHERE rand() < $p WITH collect(anchor) AS sample UNWIND sample AS anchor WITH sample, startNode(anchor) AS a, endNode(anchor) AS b MATCH (b)-[e:`FunctionalAssociation`]->(a) RETURN size(sample) AS sampleN, count(e) AS merges
// apoc.periodic.iterate: batches of 10000, committed separately; progress is reported by the App.
CALL apoc.periodic.iterate(
  // 1. DRIVING STATEMENT
  "MATCH (a)-[anchor:`QuantitativeChange`]->(b) WHERE EXISTS { MATCH (b)-[e:`FunctionalAssociation`]->(a) } RETURN anchor",

  // 2. ACTION STATEMENT
  "WITH anchor, startNode(anchor) AS a, endNode(anchor) AS b
   MATCH (b)-[assoc:`FunctionalAssociation`]->(a)
   WITH anchor, collect(assoc) AS evidence
   WITH anchor, evidence, [rb IN evidence | properties(rb)] AS assoc_props_list
   WITH anchor, evidence, assoc_props_list,
        apoc.coll.toSet(keys(properties(anchor)) + apoc.coll.flatten([m IN assoc_props_list | keys(m)])) AS all_keys
   WITH anchor, evidence,
        apoc.map.fromLists(all_keys, [k IN all_keys |
            apoc.coll.flatten([coalesce(properties(anchor)[k], [])]) +
            apoc.coll.flatten([m IN assoc_props_list | coalesce(m[k], [])])
        ]) AS mergedProps
   SET anchor = mergedProps
   WITH anchor, evidence
   UNWIND evidence AS rb
   DELETE rb",

  // 3. CONFIGURATION
  {
    batchSize: 10000,
    parallel: true,
    retries: 3,
    concurrency: 4
  }
)
YIELD committedOperations, failedOperations, errorMessages
RETURN
  "reversedFuncAssoc2QuantitativeChange" AS merge_type,
  committedOperations AS mergedCount,
  failedOperations AS failedCount,
  errorMessages AS errors

UNION

//STEP 16. Merge QuantitativeChange|FunctionalAssociation into Biomarker:
//ESTIMATE: CALL { {DRIVING} } WITH anchor WHERE rand() < $p WITH collect(anchor) AS sample UNWIND sample AS anchor WITH sample, startNode(anchor) AS a, endNode(anchor) AS b MATCH (a)-[e:`QuantitativeChange`|`FunctionalAssociation`]->(b) RETURN size(sample) AS sampleN, count(e) AS merges
// apoc.periodic.iterate: batches of 10000, committed separately; progress is reported by the App.
CALL apoc.periodic.iterate(
  // 1. DRIVING STATEMENT
  "MATCH (a)-[anchor:`Biomarker`]->(b) WHERE EXISTS { MATCH (a)-[:`QuantitativeChange`|`FunctionalAssociation`]->(b) } RETURN anchor",

  // 2. ACTION STATEMENT
  "WITH anchor, startNode(anchor) AS a, endNode(anchor) AS b
   MATCH (a)-[evidence:`QuantitativeChange`|`FunctionalAssociation`]->(b)
   WITH anchor, collect(evidence) AS evidenceRels
   CALL apoc.refactor.mergeRelationships([anchor] + evidenceRels, {properties: 'combine', produceSelfRel: false})
   YIELD rel
   RETURN count(rel) AS merged",

  // 3. CONFIGURATION
  {
    batchSize: 10000,
    parallel: true,
    retries: 3,
    concurrency: 4
  }
)
YIELD committedOperations, failedOperations, errorMessages
RETURN
  "QuanChangeFuncAssoc2Biomarker" AS merge_type,
  committedOperations AS mergedCount,
  failedOperations AS failedCount,
  errorMessages AS errors

UNION

//STEP 17. Merge reversed FunctionalAssociation to Biomarker:
//ESTIMATE: CALL { {DRIVING} } WITH anchor WHERE rand() < $p WITH collect(anchor) AS sample UNWIND sample AS anchor WITH sample, startNode(anchor) AS a, endNode(anchor) AS b MATCH (b)-[e:`FunctionalAssociation`]->(a) RETURN size(sample) AS sampleN, count(e) AS merges
// apoc.periodic.iterate: batches of 10000, committed separately; progress is reported by the App.
CALL apoc.periodic.iterate(
  // 1. DRIVING STATEMENT
  "MATCH (a)-[anchor:`Biomarker`]->(b) WHERE EXISTS { MATCH (b)-[e:`FunctionalAssociation`]->(a) } RETURN anchor",

  // 2. ACTION STATEMENT
  "WITH anchor, startNode(anchor) AS a, endNode(anchor) AS b
   MATCH (b)-[assoc:`FunctionalAssociation`]->(a)
   WITH anchor, collect(assoc) AS evidence
   WITH anchor, evidence, [rb IN evidence | properties(rb)] AS assoc_props_list
   WITH anchor, evidence, assoc_props_list,
        apoc.coll.toSet(keys(properties(anchor)) + apoc.coll.flatten([m IN assoc_props_list | keys(m)])) AS all_keys
   WITH anchor, evidence,
        apoc.map.fromLists(all_keys, [k IN all_keys |
            apoc.coll.flatten([coalesce(properties(anchor)[k], [])]) +
            apoc.coll.flatten([m IN assoc_props_list | coalesce(m[k], [])])
        ]) AS mergedProps
   SET anchor = mergedProps
   WITH anchor, evidence
   UNWIND evidence AS rb
   DELETE rb",

  // 3. CONFIGURATION
  {
    batchSize: 10000,
    parallel: true,
    retries: 3,
    concurrency: 4
  }
)
YIELD committedOperations, failedOperations, errorMessages
RETURN
  "reversedFuncAssoc2Biomarker" AS merge_type,
  committedOperations AS mergedCount,
  failedOperations AS failedCount,
  errorMessages AS errors

UNION

//STEP 18. Merge Regulation|CellExpression|FunctionalAssociation into Moltransport:
//ESTIMATE: CALL { {DRIVING} } WITH anchor WHERE rand() < $p WITH collect(anchor) AS sample UNWIND sample AS anchor WITH sample, startNode(anchor) AS a, endNode(anchor) AS b MATCH (a)-[e:`CellExpression`|`Regulation`|`FunctionalAssociation`]->(b) RETURN size(sample) AS sampleN, count(e) AS merges
// apoc.periodic.iterate: batches of 10000, committed separately; progress is reported by the App.
CALL apoc.periodic.iterate(
  // 1. DRIVING STATEMENT
  "MATCH (a)-[anchor:`MolTransport`]->(b) WHERE EXISTS { MATCH (a)-[:`CellExpression`|`Regulation`|`FunctionalAssociation`]->(b) } RETURN anchor",

  // 2. ACTION STATEMENT
  "WITH anchor, startNode(anchor) AS a, endNode(anchor) AS b
   MATCH (a)-[evidence:`CellExpression`|`Regulation`|`FunctionalAssociation`]->(b)
   WITH anchor, collect(evidence) AS evidenceRels
   CALL apoc.refactor.mergeRelationships([anchor] + evidenceRels, {properties: 'combine', produceSelfRel: false})
   YIELD rel
   WITH rel, properties(rel) AS props
   WITH rel, apoc.map.fromLists(
       keys(props),
       [k IN keys(props) |
           apoc.coll.toSet([x IN apoc.coll.flatten([props[k]]) WHERE x IS NOT NULL])
       ]
   ) AS uniqueMap
   WITH rel, apoc.map.fromLists(
       keys(uniqueMap),
       [k IN keys(uniqueMap) |
           CASE size(uniqueMap[k])
               WHEN 0 THEN null
               WHEN 1 THEN uniqueMap[k][0]
               ELSE uniqueMap[k]
           END
       ]
   ) AS finalProps
   SET rel = finalProps",

  // 3. CONFIGURATION
  {
    batchSize: 10000,
    parallel: true,
    retries: 3,
    concurrency: 4
  }
)
YIELD committedOperations, failedOperations, errorMessages
RETURN
  "FuncAssocCellExpReg2MolTransport" AS merge_type,
  committedOperations AS mergedCount,
  failedOperations AS failedCount,
  errorMessages AS errors

UNION

//STEP 19. Merge reversed CellExpression|FunctionalAssociation into MolTransport:
//ESTIMATE: CALL { {DRIVING} } WITH anchor WHERE rand() < $p WITH collect(anchor) AS sample UNWIND sample AS anchor WITH sample, startNode(anchor) AS a, endNode(anchor) AS b MATCH (b)-[e:`FunctionalAssociation`|`CellExpression`]->(a) RETURN size(sample) AS sampleN, count(e) AS merges
// apoc.periodic.iterate: batches of 10000, committed separately; progress is reported by the App.
CALL apoc.periodic.iterate(
  // 1. DRIVING STATEMENT
  "MATCH (a)-[anchor:`MolTransport`]->(b) WHERE EXISTS { MATCH (b)-[e:`FunctionalAssociation`|`CellExpression`]->(a) } RETURN anchor",

  // 2. ACTION STATEMENT
  "WITH anchor, startNode(anchor) AS a, endNode(anchor) AS b
   MATCH (b)-[assoc:`FunctionalAssociation`|`CellExpression`]->(a)
   WITH anchor, collect(assoc) AS evidence
   WITH anchor, evidence, [rb IN evidence | properties(rb)] AS assoc_props_list
   WITH anchor, evidence, assoc_props_list,
        apoc.coll.toSet(keys(properties(anchor)) + apoc.coll.flatten([m IN assoc_props_list | keys(m)])) AS all_keys
   WITH anchor, evidence,
        apoc.map.fromLists(all_keys, [k IN all_keys |
            apoc.coll.flatten([coalesce(properties(anchor)[k], [])]) +
            apoc.coll.flatten([m IN assoc_props_list | coalesce(m[k], [])])
        ]) AS mergedProps
   SET anchor = mergedProps
   WITH anchor, evidence
   UNWIND evidence AS rb
   DELETE rb",

  // 3. CONFIGURATION
  {
    batchSize: 10000,
    parallel: true,
    retries: 3,
    concurrency: 4
  }
)
YIELD committedOperations, failedOperations, errorMessages
RETURN
  "reversedFuncAssocCellExp2MolTransport" AS merge_type,
  committedOperations AS mergedCount,
  failedOperations AS failedCount,
  errorMessages AS errors

UNION

//STEP 20. Merge Regulation|FunctionalAssociation into MolSynthesis:
//ESTIMATE: CALL { {DRIVING} } WITH anchor WHERE rand() < $p WITH collect(anchor) AS sample UNWIND sample AS anchor WITH sample, startNode(anchor) AS a, endNode(anchor) AS b MATCH (a)-[e:`Regulation`|`FunctionalAssociation`]->(b) RETURN size(sample) AS sampleN, count(e) AS merges
// apoc.periodic.iterate: batches of 10000, committed separately; progress is reported by the App.
CALL apoc.periodic.iterate(
  // 1. DRIVING STATEMENT
  "MATCH (a)-[anchor:`MolSynthesis`]->(b) WHERE EXISTS { MATCH (a)-[:`Regulation`|`FunctionalAssociation`]->(b) } RETURN anchor",

  // 2. ACTION STATEMENT
  "WITH anchor, startNode(anchor) AS a, endNode(anchor) AS b
   MATCH (a)-[evidence:`Regulation`|`FunctionalAssociation`]->(b)
   WITH anchor, collect(evidence) AS evidenceRels
   CALL apoc.refactor.mergeRelationships([anchor] + evidenceRels, {properties: 'combine', produceSelfRel: false})
   YIELD rel
   WITH rel, properties(rel) AS props
   WITH rel, apoc.map.fromLists(
       keys(props),
       [k IN keys(props) |
           apoc.coll.toSet([x IN apoc.coll.flatten([props[k]]) WHERE x IS NOT NULL])
       ]
   ) AS uniqueMap
   WITH rel, apoc.map.fromLists(
       keys(uniqueMap),
       [k IN keys(uniqueMap) |
           CASE size(uniqueMap[k])
               WHEN 0 THEN null
               WHEN 1 THEN uniqueMap[k][0]
               ELSE uniqueMap[k]
           END
       ]
   ) AS finalProps
   SET rel = finalProps",

  // 3. CONFIGURATION
  {
    batchSize: 10000,
    parallel: true,
    retries: 3,
    concurrency: 4
  }
)
YIELD committedOperations, failedOperations, errorMessages
RETURN
  "FuncAssocReg2MolSynthesis" AS merge_type,
  committedOperations AS mergedCount,
  failedOperations AS failedCount,
  errorMessages AS errors

UNION

//STEP 21. Merge reversed FunctionalAssociation to MolSynthesis:
//ESTIMATE: CALL { {DRIVING} } WITH anchor WHERE rand() < $p WITH collect(anchor) AS sample UNWIND sample AS anchor WITH sample, startNode(anchor) AS a, endNode(anchor) AS b MATCH (b)-[e:`FunctionalAssociation`]->(a) RETURN size(sample) AS sampleN, count(e) AS merges
// apoc.periodic.iterate: batches of 10000, committed separately; progress is reported by the App.
CALL apoc.periodic.iterate(
  // 1. DRIVING STATEMENT
  "MATCH (a)-[anchor:`MolSynthesis`]->(b) WHERE EXISTS { MATCH (b)-[e:`FunctionalAssociation`]->(a) } RETURN anchor",

  // 2. ACTION STATEMENT
  "WITH anchor, startNode(anchor) AS a, endNode(anchor) AS b
   MATCH (b)-[assoc:`FunctionalAssociation`]->(a)
   WITH anchor, collect(assoc) AS evidence
   WITH anchor, evidence, [rb IN evidence | properties(rb)] AS assoc_props_list
   WITH anchor, evidence, assoc_props_list,
        apoc.coll.toSet(keys(properties(anchor)) + apoc.coll.flatten([m IN assoc_props_list | keys(m)])) AS all_keys
   WITH anchor, evidence,
        apoc.map.fromLists(all_keys, [k IN all_keys |
            apoc.coll.flatten([coalesce(properties(anchor)[k], [])]) +
            apoc.coll.flatten([m IN assoc_props_list | coalesce(m[k], [])])
        ]) AS mergedProps
   SET anchor = mergedProps
   WITH anchor, evidence
   UNWIND evidence AS rb
   DELETE rb",

  // 3. CONFIGURATION
  {
    batchSize: 10000,
    parallel: true,
    retries: 3,
    concurrency: 4
  }
)
YIELD committedOperations, failedOperations, errorMessages
RETURN
  "reversedFuncAssoc2MolSynthesis" AS merge_type,
  committedOperations AS mergedCount,
  failedOperations AS failedCount,
  errorMessages AS errors
//STEP 1. Merge same type relations:
// Batched: one start node at a time, committed every 10000 start nodes. The single-transaction form grouped ALL
// relations at once and exceeded dbms.memory.transaction.total.max.
CALL apoc.periodic.iterate(
  // 1. DRIVING STATEMENT
  "MATCH (a) WHERE count{(a)-->()} > 1 RETURN a",
  
  // 2. ACTION STATEMENT
  "MATCH (a)-[r]->(b)
   WHERE NOT type(r) IN ['is_a', 'part_of', 'MemberOf', 'derivative_of']
   WITH a, b, type(r) AS relType, collect(r) AS rels
   WHERE size(rels) > 1
   
   UNWIND rels AS r
   WITH a, b, relType, r
   ORDER BY coalesce(r.RelationNumberOfReferences, 0) DESC
   WITH a, b, relType, collect(r) AS sortedRels
   
   CALL apoc.refactor.mergeRelationships(sortedRels, {properties: 'combine'})
   YIELD rel
   
   WITH rel, properties(rel) AS props
   WITH rel, apoc.map.fromLists(
       keys(props),
       [k IN keys(props) |
           apoc.coll.toSet([v IN apoc.coll.flatten([props[k]]) WHERE v IS NOT NULL])
       ]
   ) AS uniqueMap
   
   WITH rel, apoc.map.fromLists(
       keys(uniqueMap),
       [k IN keys(uniqueMap) |
           CASE size(uniqueMap[k])
               WHEN 0 THEN null
               WHEN 1 THEN uniqueMap[k][0]
               ELSE uniqueMap[k]
           END
       ]
   ) AS finalProps
   
   SET rel = finalProps",
   
  // 3. CONFIGURATION
  {
    batchSize: 10000, 
    parallel: true, 
    retries: 3,
    concurrency: 4 
  }
)
// 4. CAPTURE AND FORMAT THE OUTPUT
YIELD committedOperations, failedOperations, errorMessages
RETURN 
  "Same reltype" AS merge_type,
  committedOperations AS mergedCount,
  failedOperations AS failedCount,
  errorMessages AS errors

UNION

//STEP 2. Merge FunctionalAssociation into Regulation:
//ESTIMATE: CALL { {DRIVING} } WITH anchor WHERE rand() < $p WITH collect(anchor) AS sample UNWIND sample AS anchor WITH sample, startNode(anchor) AS a, endNode(anchor) AS b MATCH (a)-[e:`FunctionalAssociation`]->(b) RETURN size(sample) AS sampleN, count(e) AS merges
// apoc.periodic.iterate: batches of 10000, committed separately; progress is reported by the App.
CALL apoc.periodic.iterate(
  // 1. DRIVING STATEMENT
  "MATCH (a)-[anchor:`Regulation`]->(b) WHERE EXISTS { MATCH (a)-[:`FunctionalAssociation`]->(b) } RETURN anchor",

  // 2. ACTION STATEMENT
  "WITH anchor, startNode(anchor) AS a, endNode(anchor) AS b
   MATCH (a)-[evidence:`FunctionalAssociation`]->(b)
   WITH anchor, collect(evidence) AS evidenceRels
   CALL apoc.refactor.mergeRelationships([anchor] + evidenceRels, {properties: 'combine', produceSelfRel: false})
   YIELD rel
   WITH rel, properties(rel) AS props
   WITH rel, apoc.map.fromLists(
       keys(props),
       [k IN keys(props) |
           apoc.coll.toSet([x IN apoc.coll.flatten([props[k]]) WHERE x IS NOT NULL])
       ]
   ) AS uniqueMap
   WITH rel, apoc.map.fromLists(
       keys(uniqueMap),
       [k IN keys(uniqueMap) |
           CASE size(uniqueMap[k])
               WHEN 0 THEN null
               WHEN 1 THEN uniqueMap[k][0]
               ELSE uniqueMap[k]
           END
       ]
   ) AS finalProps
   SET rel = finalProps",

  // 3. CONFIGURATION
  {
    batchSize: 10000,
    parallel: true,
    retries: 3,
    concurrency: 4
  }
)
YIELD committedOperations, failedOperations, errorMessages
RETURN
  "FuncAssoc2Regulation" AS merge_type,
  committedOperations AS mergedCount,
  failedOperations AS failedCount,
  errorMessages AS errors

UNION

//STEP 3. Merge reversed FunctionalAssociation into Regulation:
//ESTIMATE: CALL { {DRIVING} } WITH anchor WHERE rand() < $p WITH collect(anchor) AS sample UNWIND sample AS anchor WITH sample, startNode(anchor) AS a, endNode(anchor) AS b MATCH (b)-[e:`FunctionalAssociation`]->(a) RETURN size(sample) AS sampleN, count(e) AS merges
// apoc.periodic.iterate: batches of 10000, committed separately; progress is reported by the App.
CALL apoc.periodic.iterate(
  // 1. DRIVING STATEMENT
  "MATCH (a)-[anchor:`Regulation`]->(b) WHERE EXISTS { MATCH (b)-[e:`FunctionalAssociation`]->(a) } RETURN anchor",

  // 2. ACTION STATEMENT
  "WITH anchor, startNode(anchor) AS a, endNode(anchor) AS b
   MATCH (b)-[assoc:`FunctionalAssociation`]->(a)
   WITH anchor, collect(assoc) AS evidence
   WITH anchor, evidence, [rb IN evidence | properties(rb)] AS assoc_props_list
   WITH anchor, evidence, assoc_props_list,
        apoc.coll.toSet(keys(properties(anchor)) + apoc.coll.flatten([m IN assoc_props_list | keys(m)])) AS all_keys
   WITH anchor, evidence,
        apoc.map.fromLists(all_keys, [k IN all_keys |
            apoc.coll.flatten([coalesce(properties(anchor)[k], [])]) +
            apoc.coll.flatten([m IN assoc_props_list | coalesce(m[k], [])])
        ]) AS mergedProps
   SET anchor = mergedProps
   WITH anchor, evidence
   UNWIND evidence AS rb
   DELETE rb",

  // 3. CONFIGURATION
  {
    batchSize: 10000,
    parallel: true,
    retries: 3,
    concurrency: 4
  }
)
YIELD committedOperations, failedOperations, errorMessages
RETURN
  "reversedFuncAssoc2Regulation" AS merge_type,
  committedOperations AS mergedCount,
  failedOperations AS failedCount,
  errorMessages AS errors

UNION

//STEP 4. Create DirectRegulation from Binding + Regulation:
//ESTIMATE: CALL { {DRIVING} } WITH a WHERE rand() < $p WITH collect(a) AS sample UNWIND sample AS a MATCH (a)-[r:`Regulation`|`Binding`]->(b) WHERE r.RelationNumberOfReferences > 1 WITH sample, a, b, count(r) AS c WHERE c > 1 RETURN size(sample) AS sampleN, sum(c - 1) AS merges
// apoc.periodic.iterate: batches of 10000, committed separately; progress is reported by the App.
CALL apoc.periodic.iterate(
  // 1. DRIVING STATEMENT
  "MATCH (a) WHERE count{ (a)-[r:`Regulation`|`Binding`]->() WHERE r.RelationNumberOfReferences > 1 } > 1 RETURN a",

  // 2. ACTION STATEMENT
  "MATCH (a)-[r:`Regulation`|`Binding`]->(b)
   WHERE r.RelationNumberOfReferences > 1
   WITH a, b, collect(r) AS rels
   WHERE size(rels) > 1
   UNWIND rels AS r
   WITH a, b, r
   ORDER BY coalesce(r.RelationNumberOfReferences, 0) DESC
   WITH a, b, collect(r) AS sortedRels
   WITH a, b, sortedRels, properties(sortedRels[0]) AS baseProps
   CREATE (a)-[newRel:DirectRegulation]->(b)
   SET newRel = baseProps
   WITH newRel, sortedRels
   CALL apoc.refactor.mergeRelationships([newRel] + sortedRels, {properties: 'combine', produceSelfRel: false})
   YIELD rel
   WITH rel, properties(rel) AS props
   WITH rel, apoc.map.fromLists(
       keys(props),
       [k IN keys(props) |
           apoc.coll.toSet([x IN apoc.coll.flatten([props[k]]) WHERE x IS NOT NULL])
       ]
   ) AS uniqueMap
   WITH rel, apoc.map.fromLists(
       keys(uniqueMap),
       [k IN keys(uniqueMap) |
           CASE size(uniqueMap[k])
               WHEN 0 THEN null
               WHEN 1 THEN uniqueMap[k][0]
               ELSE uniqueMap[k]
           END
       ]
   ) AS finalProps
   SET rel = finalProps",

  // 3. CONFIGURATION
  {
    batchSize: 10000,
    parallel: true,
    retries: 3,
    concurrency: 4
  }
)
YIELD committedOperations, failedOperations, errorMessages
RETURN
  "createDirectRegulation" AS merge_type,
  committedOperations AS mergedCount,
  failedOperations AS failedCount,
  errorMessages AS errors

UNION

//STEP 5. Create DirectRegulation from reversed Binding + Regulation:
//ESTIMATE: CALL { {DRIVING} } WITH a, b WHERE rand() < $p WITH collect([a, b]) AS sample UNWIND sample AS ab WITH sample, ab[0] AS a, ab[1] AS b MATCH (a)-[reg:Regulation]->(b) WITH sample, a, b, count(reg) AS regs MATCH (b)-[bind:Binding]->(a) WHERE bind.RelationNumberOfReferences > 2 WITH sample, a, b, regs, count(bind) AS binds RETURN size(sample) AS sampleN, sum(regs + binds - 1) AS merges
// apoc.periodic.iterate: batches of 10000, committed separately; progress is reported by the App.
CALL apoc.periodic.iterate(
  // 1. DRIVING STATEMENT
  "MATCH (a)-[:Regulation]->(b) WHERE EXISTS { MATCH (b)-[bd:Binding]->(a) WHERE bd.RelationNumberOfReferences > 2 } RETURN DISTINCT a, b",

  // 2. ACTION STATEMENT
  "MATCH (a)-[reg:Regulation]->(b)
   MATCH (b)-[bind:Binding]->(a)
   WHERE bind.RelationNumberOfReferences > 2
   WITH a, b, collect(DISTINCT reg) AS regs, collect(DISTINCT bind) AS rev_binds
   WITH a, b, regs, rev_binds,
        [r IN regs + rev_binds | properties(r)] AS all_props_maps
   WITH a, b, regs, rev_binds, all_props_maps,
        apoc.coll.toSet(apoc.coll.flatten([m IN all_props_maps | keys(m)])) AS all_keys
   WITH a, b, regs, rev_binds,
        apoc.map.fromLists(all_keys, [k IN all_keys |
           apoc.coll.flatten([m IN all_props_maps | coalesce(m[k], [])])
        ]) AS combinedProps
   CREATE (a)-[newRel:DirectRegulation]->(b)
   SET newRel = combinedProps
   WITH regs, rev_binds, newRel
   FOREACH (r IN regs | DELETE r)
   FOREACH (rb IN rev_binds | DELETE rb)
   WITH newRel, properties(newRel) AS props
   WITH newRel, apoc.map.fromLists(
       keys(props),
       [k IN keys(props) |
           apoc.coll.toSet([x IN apoc.coll.flatten([props[k]]) WHERE x IS NOT NULL])
       ]
   ) AS uniqueMap
   WITH newRel, apoc.map.fromLists(
       keys(uniqueMap),
       [k IN keys(uniqueMap) |
           CASE size(uniqueMap[k])
               WHEN 0 THEN null
               WHEN 1 THEN uniqueMap[k][0]
               ELSE uniqueMap[k]
           END
       ]
   ) AS finalProps
   SET newRel = finalProps",

  // 3. CONFIGURATION
  {
    batchSize: 10000,
    parallel: true,
    retries: 3,
    concurrency: 4
  }
)
YIELD committedOperations, failedOperations, errorMessages
RETURN
  "createDirectRegulationReversedBinding" AS merge_type,
  committedOperations AS mergedCount,
  failedOperations AS failedCount,
  errorMessages AS errors

UNION

//STEP 6. Merge new DirectRegulation:
//ESTIMATE: CALL { {DRIVING} } WITH a WHERE rand() < $p WITH collect(a) AS sample UNWIND sample AS a MATCH (a)-[r:`DirectRegulation`]->(b) WITH sample, a, b, count(r) AS c WHERE c > 1 RETURN size(sample) AS sampleN, sum(c - 1) AS merges
// apoc.periodic.iterate: batches of 10000, committed separately; progress is reported by the App.
CALL apoc.periodic.iterate(
  // 1. DRIVING STATEMENT
  "MATCH (a) WHERE count{(a)-[:`DirectRegulation`]->()} > 1 RETURN a",

  // 2. ACTION STATEMENT
  "MATCH (a)-[r:`DirectRegulation`]->(b)
   WITH a, b, collect(r) AS rels
   WHERE size(rels) > 1
   UNWIND rels AS r
   WITH a, b, r
   ORDER BY coalesce(r.RelationNumberOfReferences, 0) DESC
   WITH a, b, collect(r) AS sortedRels
   CALL apoc.refactor.mergeRelationships(sortedRels, {properties: 'combine'})
   YIELD rel
   WITH rel, properties(rel) AS props
   WITH rel, apoc.map.fromLists(
       keys(props),
       [k IN keys(props) |
           apoc.coll.toSet([x IN apoc.coll.flatten([props[k]]) WHERE x IS NOT NULL])
       ]
   ) AS uniqueMap
   WITH rel, apoc.map.fromLists(
       keys(uniqueMap),
       [k IN keys(uniqueMap) |
           CASE size(uniqueMap[k])
               WHEN 0 THEN null
               WHEN 1 THEN uniqueMap[k][0]
               ELSE uniqueMap[k]
           END
       ]
   ) AS finalProps
   SET rel = finalProps",

  // 3. CONFIGURATION
  {
    batchSize: 10000,
    parallel: true,
    retries: 3,
    concurrency: 4
  }
)
YIELD committedOperations, failedOperations, errorMessages
RETURN
  "Same reltype after DirectRegulation" AS merge_type,
  committedOperations AS mergedCount,
  failedOperations AS failedCount,
  errorMessages AS errors

UNION

//STEP 7. Convert ProtModification to Regulation for non-enzymes:
// parallel: false because every row creates and deletes a relationship, and parallel batches deadlocked on shared nodes.
// apoc.periodic.iterate: batches of 10000, committed separately; progress is reported by the App.
CALL apoc.periodic.iterate(
  // 1. DRIVING STATEMENT
  "MATCH (p) WHERE p.Name IN ['protein kinase', 'acetyltransferase', 'peptide hydrolase', 'deacetylase', 'protein methyltransferase', 'histone modification enzyme', 'aminoacyltransferase', 'peptide synthase', 'protein phosphatase'] OPTIONAL MATCH (child)-[:is_a*]->(p) WITH collect(DISTINCT child) + collect(DISTINCT p) AS enzymeNodes MATCH (n)-[r:ProtModification]->(t) WHERE NOT n IN enzymeNodes RETURN r",

  // 2. ACTION STATEMENT
  "WITH r, startNode(r) AS n, endNode(r) AS t, properties(r) AS oldProps
   CREATE (n)-[newRel:Regulation]->(t)
   SET newRel = oldProps
   DELETE r",

  // 3. CONFIGURATION
  {
    batchSize: 10000,
    parallel: false,
    retries: 3
  }
)
YIELD committedOperations, failedOperations, errorMessages
RETURN
  "ConvertProtMod2Regulation" AS merge_type,
  committedOperations AS mergedCount,
  failedOperations AS failedCount,
  errorMessages AS errors

UNION

//STEP 8. Merge Regulation into ProtModification for enzymes:
//ESTIMATE: CALL { {DRIVING} } WITH enzyme WHERE rand() < $p WITH collect(enzyme) AS sample UNWIND sample AS enzyme MATCH (enzyme)-[r1:ProtModification]->(b) MATCH (enzyme)-[r2:Regulation]->(b) WITH sample, enzyme, b, count(DISTINCT r1) + count(DISTINCT r2) AS c RETURN size(sample) AS sampleN, sum(c - 1) AS merges
// apoc.periodic.iterate: batches of 10000, committed separately; progress is reported by the App.
CALL apoc.periodic.iterate(
  // 1. DRIVING STATEMENT
  "MATCH (p) WHERE p.Name IN ['protein kinase', 'acetyltransferase', 'peptide hydrolase', 'deacetylase', 'protein methyltransferase', 'histone modification enzyme', 'aminoacyltransferase', 'peptide synthase', 'protein phosphatase'] OPTIONAL MATCH (child)-[:is_a*]->(p) WITH collect(DISTINCT p) + collect(DISTINCT child) AS all_enzymes UNWIND all_enzymes AS enzyme WITH DISTINCT enzyme WHERE EXISTS { MATCH (enzyme)-[:ProtModification]->()<-[:Regulation]-(enzyme) } RETURN enzyme",

  // 2. ACTION STATEMENT
  "MATCH (enzyme)-[r1:ProtModification]->(b)
   MATCH (enzyme)-[r2:Regulation]->(b)
   WITH enzyme, b, collect(DISTINCT r1) + collect(DISTINCT r2) AS rels
   UNWIND rels AS r
   WITH enzyme, b, r
   ORDER BY
     CASE type(r)
       WHEN 'ProtModification' THEN 1
       WHEN 'Regulation' THEN 2
     END ASC,
     coalesce(r.RelationNumberOfReferences, 0) DESC
   WITH enzyme, b, collect(r) AS sortedRels
   CALL apoc.refactor.mergeRelationships(sortedRels, {properties: 'combine'})
   YIELD rel
   WITH rel, properties(rel) AS props
   WITH rel, apoc.map.fromLists(
       keys(props),
       [k IN keys(props) |
           apoc.coll.toSet([x IN apoc.coll.flatten([props[k]]) WHERE x IS NOT NULL])
       ]
   ) AS uniqueMap
   WITH rel, apoc.map.fromLists(
       keys(uniqueMap),
       [k IN keys(uniqueMap) |
           CASE size(uniqueMap[k])
               WHEN 0 THEN null
               WHEN 1 THEN uniqueMap[k][0]
               ELSE uniqueMap[k]
           END
       ]
   ) AS finalProps
   SET rel = finalProps",

  // 3. CONFIGURATION
  {
    batchSize: 10000,
    parallel: true,
    retries: 3,
    concurrency: 4
  }
)
YIELD committedOperations, failedOperations, errorMessages
RETURN
  "Regulation2ProtMod" AS merge_type,
  committedOperations AS mergedCount,
  failedOperations AS failedCount,
  errorMessages AS errors

UNION

//STEP 9. Merge Regulation|Binding|ProtModification into DirectRegulation:
//ESTIMATE: CALL { {DRIVING} } WITH anchor WHERE rand() < $p WITH collect(anchor) AS sample UNWIND sample AS anchor WITH sample, startNode(anchor) AS a, endNode(anchor) AS b MATCH (a)-[e:`Regulation`|`Binding`|`ProtModification`]->(b) RETURN size(sample) AS sampleN, count(e) AS merges
// apoc.periodic.iterate: batches of 10000, committed separately; progress is reported by the App.
CALL apoc.periodic.iterate(
  // 1. DRIVING STATEMENT
  "MATCH (a)-[anchor:`DirectRegulation`]->(b) WHERE EXISTS { MATCH (a)-[:`Regulation`|`Binding`|`ProtModification`]->(b) } RETURN anchor",

  // 2. ACTION STATEMENT
  "WITH anchor, startNode(anchor) AS a, endNode(anchor) AS b
   MATCH (a)-[evidence:`Regulation`|`Binding`|`ProtModification`]->(b)
   WITH anchor, collect(evidence) AS evidenceRels
   CALL apoc.refactor.mergeRelationships([anchor] + evidenceRels, {properties: 'combine', produceSelfRel: false})
   YIELD rel
   WITH rel, properties(rel) AS props
   WITH rel, apoc.map.fromLists(
       keys(props),
       [k IN keys(props) |
           apoc.coll.toSet([x IN apoc.coll.flatten([props[k]]) WHERE x IS NOT NULL])
       ]
   ) AS uniqueMap
   WITH rel, apoc.map.fromLists(
       keys(uniqueMap),
       [k IN keys(uniqueMap) |
           CASE size(uniqueMap[k])
               WHEN 0 THEN null
               WHEN 1 THEN uniqueMap[k][0]
               ELSE uniqueMap[k]
           END
       ]
   ) AS finalProps
   SET rel = finalProps",

  // 3. CONFIGURATION
  {
    batchSize: 10000,
    parallel: true,
    retries: 3,
    concurrency: 4
  }
)
YIELD committedOperations, failedOperations, errorMessages
RETURN
  "RegProtModBind2DirectRegulation" AS merge_type,
  committedOperations AS mergedCount,
  failedOperations AS failedCount,
  errorMessages AS errors

UNION

//STEP 10. Merge reversed Binding to DirectRegulation:
//ESTIMATE: CALL { {DRIVING} } WITH anchor WHERE rand() < $p WITH collect(anchor) AS sample UNWIND sample AS anchor WITH sample, startNode(anchor) AS a, endNode(anchor) AS b MATCH (b)-[e:`Binding`]->(a) WHERE e.RelationNumberOfReferences > 2 RETURN size(sample) AS sampleN, count(e) AS merges
// apoc.periodic.iterate: batches of 10000, committed separately; progress is reported by the App.
CALL apoc.periodic.iterate(
  // 1. DRIVING STATEMENT
  "MATCH (a)-[anchor:`DirectRegulation`]->(b) WHERE EXISTS { MATCH (b)-[e:`Binding`]->(a) WHERE e.RelationNumberOfReferences > 2 } RETURN anchor",

  // 2. ACTION STATEMENT
  "WITH anchor, startNode(anchor) AS a, endNode(anchor) AS b
   MATCH (b)-[assoc:`Binding`]->(a)
   WHERE assoc.RelationNumberOfReferences > 2
   WITH anchor, collect(assoc) AS evidence
   WITH anchor, evidence, [rb IN evidence | properties(rb)] AS assoc_props_list
   WITH anchor, evidence, assoc_props_list,
        apoc.coll.toSet(keys(properties(anchor)) + apoc.coll.flatten([m IN assoc_props_list | keys(m)])) AS all_keys
   WITH anchor, evidence,
        apoc.map.fromLists(all_keys, [k IN all_keys |
            apoc.coll.flatten([coalesce(properties(anchor)[k], [])]) +
            apoc.coll.flatten([m IN assoc_props_list | coalesce(m[k], [])])
        ]) AS mergedProps
   SET anchor = mergedProps
   WITH anchor, evidence
   UNWIND evidence AS rb
   DELETE rb",

  // 3. CONFIGURATION
  {
    batchSize: 10000,
    parallel: true,
    retries: 3,
    concurrency: 4
  }
)
YIELD committedOperations, failedOperations, errorMessages
RETURN
  "reversedBind2DirectRegulation" AS merge_type,
  committedOperations AS mergedCount,
  failedOperations AS failedCount,
  errorMessages AS errors

UNION

//STEP 11. Merge Regulation|FunctionalAssociation to Expression:
//ESTIMATE: CALL { {DRIVING} } WITH anchor WHERE rand() < $p WITH collect(anchor) AS sample UNWIND sample AS anchor WITH sample, startNode(anchor) AS a, endNode(anchor) AS b MATCH (a)-[e:`Regulation`|`FunctionalAssociation`]->(b) RETURN size(sample) AS sampleN, count(e) AS merges
// apoc.periodic.iterate: batches of 10000, committed separately; progress is reported by the App.
CALL apoc.periodic.iterate(
  // 1. DRIVING STATEMENT
  "MATCH (a)-[anchor:`Expression`]->(b) WHERE EXISTS { MATCH (a)-[:`Regulation`|`FunctionalAssociation`]->(b) } RETURN anchor",

  // 2. ACTION STATEMENT
  "WITH anchor, startNode(anchor) AS a, endNode(anchor) AS b
   MATCH (a)-[evidence:`Regulation`|`FunctionalAssociation`]->(b)
   WITH anchor, collect(evidence) AS evidenceRels
   CALL apoc.refactor.mergeRelationships([anchor] + evidenceRels, {properties: 'combine', produceSelfRel: false})
   YIELD rel
   WITH rel, properties(rel) AS props
   WITH rel, apoc.map.fromLists(
       keys(props),
       [k IN keys(props) |
           apoc.coll.toSet([x IN apoc.coll.flatten([props[k]]) WHERE x IS NOT NULL])
       ]
   ) AS uniqueMap
   WITH rel, apoc.map.fromLists(
       keys(uniqueMap),
       [k IN keys(uniqueMap) |
           CASE size(uniqueMap[k])
               WHEN 0 THEN null
               WHEN 1 THEN uniqueMap[k][0]
               ELSE uniqueMap[k]
           END
       ]
   ) AS finalProps
   SET rel = finalProps",

  // 3. CONFIGURATION
  {
    batchSize: 10000,
    parallel: true,
    retries: 3,
    concurrency: 4
  }
)
YIELD committedOperations, failedOperations, errorMessages
RETURN
  "RegFuncAssoc2Expression" AS merge_type,
  committedOperations AS mergedCount,
  failedOperations AS failedCount,
  errorMessages AS errors

UNION

//STEP 12. Merge reversed FunctionalAssociation into Expression
//ESTIMATE: CALL { {DRIVING} } WITH anchor WHERE rand() < $p WITH collect(anchor) AS sample UNWIND sample AS anchor WITH sample, startNode(anchor) AS a, endNode(anchor) AS b MATCH (b)-[e:`FunctionalAssociation`]->(a) RETURN size(sample) AS sampleN, count(e) AS merges
// apoc.periodic.iterate: batches of 10000, committed separately; progress is reported by the App.
CALL apoc.periodic.iterate(
  // 1. DRIVING STATEMENT
  "MATCH (a)-[anchor:`Expression`]->(b) WHERE EXISTS { MATCH (b)-[e:`FunctionalAssociation`]->(a) } RETURN anchor",

  // 2. ACTION STATEMENT
  "WITH anchor, startNode(anchor) AS a, endNode(anchor) AS b
   MATCH (b)-[assoc:`FunctionalAssociation`]->(a)
   WITH anchor, collect(assoc) AS evidence
   WITH anchor, evidence, [rb IN evidence | properties(rb)] AS assoc_props_list
   WITH anchor, evidence, assoc_props_list,
        apoc.coll.toSet(keys(properties(anchor)) + apoc.coll.flatten([m IN assoc_props_list | keys(m)])) AS all_keys
   WITH anchor, evidence,
        apoc.map.fromLists(all_keys, [k IN all_keys |
            apoc.coll.flatten([coalesce(properties(anchor)[k], [])]) +
            apoc.coll.flatten([m IN assoc_props_list | coalesce(m[k], [])])
        ]) AS mergedProps
   SET anchor = mergedProps
   WITH anchor, evidence
   UNWIND evidence AS rb
   DELETE rb",

  // 3. CONFIGURATION
  {
    batchSize: 10000,
    parallel: true,
    retries: 3,
    concurrency: 4
  }
)
YIELD committedOperations, failedOperations, errorMessages
RETURN
  "reversedFuncAssoc2Expression" AS merge_type,
  committedOperations AS mergedCount,
  failedOperations AS failedCount,
  errorMessages AS errors

UNION

//STEP 13. Merge Regulation|Expression to PromoterBinding:
//ESTIMATE: CALL { {DRIVING} } WITH anchor WHERE rand() < $p WITH collect(anchor) AS sample UNWIND sample AS anchor WITH sample, startNode(anchor) AS a, endNode(anchor) AS b MATCH (a)-[e:`Regulation`|`Expression`]->(b) RETURN size(sample) AS sampleN, count(e) AS merges
// apoc.periodic.iterate: batches of 10000, committed separately; progress is reported by the App.
CALL apoc.periodic.iterate(
  // 1. DRIVING STATEMENT
  "MATCH (a)-[anchor:`PromoterBinding`]->(b) WHERE EXISTS { MATCH (a)-[:`Regulation`|`Expression`]->(b) } RETURN anchor",

  // 2. ACTION STATEMENT
  "WITH anchor, startNode(anchor) AS a, endNode(anchor) AS b
   MATCH (a)-[evidence:`Regulation`|`Expression`]->(b)
   WITH anchor, collect(evidence) AS evidenceRels
   CALL apoc.refactor.mergeRelationships([anchor] + evidenceRels, {properties: 'combine', produceSelfRel: false})
   YIELD rel
   RETURN count(rel) AS merged",

  // 3. CONFIGURATION
  {
    batchSize: 10000,
    parallel: true,
    retries: 3,
    concurrency: 4
  }
)
YIELD committedOperations, failedOperations, errorMessages
RETURN
  "RegExpr2PromoterBinding" AS merge_type,
  committedOperations AS mergedCount,
  failedOperations AS failedCount,
  errorMessages AS errors

UNION

//STEP 14. Merge FunctionalAssociation into QuantitativeChange:
//ESTIMATE: CALL { {DRIVING} } WITH anchor WHERE rand() < $p WITH collect(anchor) AS sample UNWIND sample AS anchor WITH sample, startNode(anchor) AS a, endNode(anchor) AS b MATCH (a)-[e:`FunctionalAssociation`]->(b) RETURN size(sample) AS sampleN, count(e) AS merges
// apoc.periodic.iterate: batches of 10000, committed separately; progress is reported by the App.
CALL apoc.periodic.iterate(
  // 1. DRIVING STATEMENT
  "MATCH (a)-[anchor:`QuantitativeChange`]->(b) WHERE EXISTS { MATCH (a)-[:`FunctionalAssociation`]->(b) } RETURN anchor",

  // 2. ACTION STATEMENT
  "WITH anchor, startNode(anchor) AS a, endNode(anchor) AS b
   MATCH (a)-[evidence:`FunctionalAssociation`]->(b)
   WITH anchor, collect(evidence) AS evidenceRels
   CALL apoc.refactor.mergeRelationships([anchor] + evidenceRels, {properties: 'combine', produceSelfRel: false})
   YIELD rel
   RETURN count(rel) AS merged",

  // 3. CONFIGURATION
  {
    batchSize: 10000,
    parallel: true,
    retries: 3,
    concurrency: 4
  }
)
YIELD committedOperations, failedOperations, errorMessages
RETURN
  "FuncAssoc2QuantitativeChange" AS merge_type,
  committedOperations AS mergedCount,
  failedOperations AS failedCount,
  errorMessages AS errors

UNION

//STEP 15. Merge reversed FunctionalAssociation into QuantitativeChange
//ESTIMATE: CALL { {DRIVING} } WITH anchor WHERE rand() < $p WITH collect(anchor) AS sample UNWIND sample AS anchor WITH sample, startNode(anchor) AS a, endNode(anchor) AS b MATCH (b)-[e:`FunctionalAssociation`]->(a) RETURN size(sample) AS sampleN, count(e) AS merges
// apoc.periodic.iterate: batches of 10000, committed separately; progress is reported by the App.
CALL apoc.periodic.iterate(
  // 1. DRIVING STATEMENT
  "MATCH (a)-[anchor:`QuantitativeChange`]->(b) WHERE EXISTS { MATCH (b)-[e:`FunctionalAssociation`]->(a) } RETURN anchor",

  // 2. ACTION STATEMENT
  "WITH anchor, startNode(anchor) AS a, endNode(anchor) AS b
   MATCH (b)-[assoc:`FunctionalAssociation`]->(a)
   WITH anchor, collect(assoc) AS evidence
   WITH anchor, evidence, [rb IN evidence | properties(rb)] AS assoc_props_list
   WITH anchor, evidence, assoc_props_list,
        apoc.coll.toSet(keys(properties(anchor)) + apoc.coll.flatten([m IN assoc_props_list | keys(m)])) AS all_keys
   WITH anchor, evidence,
        apoc.map.fromLists(all_keys, [k IN all_keys |
            apoc.coll.flatten([coalesce(properties(anchor)[k], [])]) +
            apoc.coll.flatten([m IN assoc_props_list | coalesce(m[k], [])])
        ]) AS mergedProps
   SET anchor = mergedProps
   WITH anchor, evidence
   UNWIND evidence AS rb
   DELETE rb",

  // 3. CONFIGURATION
  {
    batchSize: 10000,
    parallel: true,
    retries: 3,
    concurrency: 4
  }
)
YIELD committedOperations, failedOperations, errorMessages
RETURN
  "reversedFuncAssoc2QuantitativeChange" AS merge_type,
  committedOperations AS mergedCount,
  failedOperations AS failedCount,
  errorMessages AS errors

UNION

//STEP 16. Merge QuantitativeChange|FunctionalAssociation into Biomarker:
//ESTIMATE: CALL { {DRIVING} } WITH anchor WHERE rand() < $p WITH collect(anchor) AS sample UNWIND sample AS anchor WITH sample, startNode(anchor) AS a, endNode(anchor) AS b MATCH (a)-[e:`QuantitativeChange`|`FunctionalAssociation`]->(b) RETURN size(sample) AS sampleN, count(e) AS merges
// apoc.periodic.iterate: batches of 10000, committed separately; progress is reported by the App.
CALL apoc.periodic.iterate(
  // 1. DRIVING STATEMENT
  "MATCH (a)-[anchor:`Biomarker`]->(b) WHERE EXISTS { MATCH (a)-[:`QuantitativeChange`|`FunctionalAssociation`]->(b) } RETURN anchor",

  // 2. ACTION STATEMENT
  "WITH anchor, startNode(anchor) AS a, endNode(anchor) AS b
   MATCH (a)-[evidence:`QuantitativeChange`|`FunctionalAssociation`]->(b)
   WITH anchor, collect(evidence) AS evidenceRels
   CALL apoc.refactor.mergeRelationships([anchor] + evidenceRels, {properties: 'combine', produceSelfRel: false})
   YIELD rel
   RETURN count(rel) AS merged",

  // 3. CONFIGURATION
  {
    batchSize: 10000,
    parallel: true,
    retries: 3,
    concurrency: 4
  }
)
YIELD committedOperations, failedOperations, errorMessages
RETURN
  "QuanChangeFuncAssoc2Biomarker" AS merge_type,
  committedOperations AS mergedCount,
  failedOperations AS failedCount,
  errorMessages AS errors

UNION

//STEP 17. Merge reversed FunctionalAssociation to Biomarker:
//ESTIMATE: CALL { {DRIVING} } WITH anchor WHERE rand() < $p WITH collect(anchor) AS sample UNWIND sample AS anchor WITH sample, startNode(anchor) AS a, endNode(anchor) AS b MATCH (b)-[e:`FunctionalAssociation`]->(a) RETURN size(sample) AS sampleN, count(e) AS merges
// apoc.periodic.iterate: batches of 10000, committed separately; progress is reported by the App.
CALL apoc.periodic.iterate(
  // 1. DRIVING STATEMENT
  "MATCH (a)-[anchor:`Biomarker`]->(b) WHERE EXISTS { MATCH (b)-[e:`FunctionalAssociation`]->(a) } RETURN anchor",

  // 2. ACTION STATEMENT
  "WITH anchor, startNode(anchor) AS a, endNode(anchor) AS b
   MATCH (b)-[assoc:`FunctionalAssociation`]->(a)
   WITH anchor, collect(assoc) AS evidence
   WITH anchor, evidence, [rb IN evidence | properties(rb)] AS assoc_props_list
   WITH anchor, evidence, assoc_props_list,
        apoc.coll.toSet(keys(properties(anchor)) + apoc.coll.flatten([m IN assoc_props_list | keys(m)])) AS all_keys
   WITH anchor, evidence,
        apoc.map.fromLists(all_keys, [k IN all_keys |
            apoc.coll.flatten([coalesce(properties(anchor)[k], [])]) +
            apoc.coll.flatten([m IN assoc_props_list | coalesce(m[k], [])])
        ]) AS mergedProps
   SET anchor = mergedProps
   WITH anchor, evidence
   UNWIND evidence AS rb
   DELETE rb",

  // 3. CONFIGURATION
  {
    batchSize: 10000,
    parallel: true,
    retries: 3,
    concurrency: 4
  }
)
YIELD committedOperations, failedOperations, errorMessages
RETURN
  "reversedFuncAssoc2Biomarker" AS merge_type,
  committedOperations AS mergedCount,
  failedOperations AS failedCount,
  errorMessages AS errors

UNION

//STEP 18. Merge Regulation|CellExpression|FunctionalAssociation into Moltransport:
//ESTIMATE: CALL { {DRIVING} } WITH anchor WHERE rand() < $p WITH collect(anchor) AS sample UNWIND sample AS anchor WITH sample, startNode(anchor) AS a, endNode(anchor) AS b MATCH (a)-[e:`CellExpression`|`Regulation`|`FunctionalAssociation`]->(b) RETURN size(sample) AS sampleN, count(e) AS merges
// apoc.periodic.iterate: batches of 10000, committed separately; progress is reported by the App.
CALL apoc.periodic.iterate(
  // 1. DRIVING STATEMENT
  "MATCH (a)-[anchor:`MolTransport`]->(b) WHERE EXISTS { MATCH (a)-[:`CellExpression`|`Regulation`|`FunctionalAssociation`]->(b) } RETURN anchor",

  // 2. ACTION STATEMENT
  "WITH anchor, startNode(anchor) AS a, endNode(anchor) AS b
   MATCH (a)-[evidence:`CellExpression`|`Regulation`|`FunctionalAssociation`]->(b)
   WITH anchor, collect(evidence) AS evidenceRels
   CALL apoc.refactor.mergeRelationships([anchor] + evidenceRels, {properties: 'combine', produceSelfRel: false})
   YIELD rel
   WITH rel, properties(rel) AS props
   WITH rel, apoc.map.fromLists(
       keys(props),
       [k IN keys(props) |
           apoc.coll.toSet([x IN apoc.coll.flatten([props[k]]) WHERE x IS NOT NULL])
       ]
   ) AS uniqueMap
   WITH rel, apoc.map.fromLists(
       keys(uniqueMap),
       [k IN keys(uniqueMap) |
           CASE size(uniqueMap[k])
               WHEN 0 THEN null
               WHEN 1 THEN uniqueMap[k][0]
               ELSE uniqueMap[k]
           END
       ]
   ) AS finalProps
   SET rel = finalProps",

  // 3. CONFIGURATION
  {
    batchSize: 10000,
    parallel: true,
    retries: 3,
    concurrency: 4
  }
)
YIELD committedOperations, failedOperations, errorMessages
RETURN
  "FuncAssocCellExpReg2MolTransport" AS merge_type,
  committedOperations AS mergedCount,
  failedOperations AS failedCount,
  errorMessages AS errors

UNION

//STEP 19. Merge reversed CellExpression|FunctionalAssociation into MolTransport:
//ESTIMATE: CALL { {DRIVING} } WITH anchor WHERE rand() < $p WITH collect(anchor) AS sample UNWIND sample AS anchor WITH sample, startNode(anchor) AS a, endNode(anchor) AS b MATCH (b)-[e:`FunctionalAssociation`|`CellExpression`]->(a) RETURN size(sample) AS sampleN, count(e) AS merges
// apoc.periodic.iterate: batches of 10000, committed separately; progress is reported by the App.
CALL apoc.periodic.iterate(
  // 1. DRIVING STATEMENT
  "MATCH (a)-[anchor:`MolTransport`]->(b) WHERE EXISTS { MATCH (b)-[e:`FunctionalAssociation`|`CellExpression`]->(a) } RETURN anchor",

  // 2. ACTION STATEMENT
  "WITH anchor, startNode(anchor) AS a, endNode(anchor) AS b
   MATCH (b)-[assoc:`FunctionalAssociation`|`CellExpression`]->(a)
   WITH anchor, collect(assoc) AS evidence
   WITH anchor, evidence, [rb IN evidence | properties(rb)] AS assoc_props_list
   WITH anchor, evidence, assoc_props_list,
        apoc.coll.toSet(keys(properties(anchor)) + apoc.coll.flatten([m IN assoc_props_list | keys(m)])) AS all_keys
   WITH anchor, evidence,
        apoc.map.fromLists(all_keys, [k IN all_keys |
            apoc.coll.flatten([coalesce(properties(anchor)[k], [])]) +
            apoc.coll.flatten([m IN assoc_props_list | coalesce(m[k], [])])
        ]) AS mergedProps
   SET anchor = mergedProps
   WITH anchor, evidence
   UNWIND evidence AS rb
   DELETE rb",

  // 3. CONFIGURATION
  {
    batchSize: 10000,
    parallel: true,
    retries: 3,
    concurrency: 4
  }
)
YIELD committedOperations, failedOperations, errorMessages
RETURN
  "reversedFuncAssocCellExp2MolTransport" AS merge_type,
  committedOperations AS mergedCount,
  failedOperations AS failedCount,
  errorMessages AS errors

UNION

//STEP 20. Merge Regulation|FunctionalAssociation into MolSynthesis:
//ESTIMATE: CALL { {DRIVING} } WITH anchor WHERE rand() < $p WITH collect(anchor) AS sample UNWIND sample AS anchor WITH sample, startNode(anchor) AS a, endNode(anchor) AS b MATCH (a)-[e:`Regulation`|`FunctionalAssociation`]->(b) RETURN size(sample) AS sampleN, count(e) AS merges
// apoc.periodic.iterate: batches of 10000, committed separately; progress is reported by the App.
CALL apoc.periodic.iterate(
  // 1. DRIVING STATEMENT
  "MATCH (a)-[anchor:`MolSynthesis`]->(b) WHERE EXISTS { MATCH (a)-[:`Regulation`|`FunctionalAssociation`]->(b) } RETURN anchor",

  // 2. ACTION STATEMENT
  "WITH anchor, startNode(anchor) AS a, endNode(anchor) AS b
   MATCH (a)-[evidence:`Regulation`|`FunctionalAssociation`]->(b)
   WITH anchor, collect(evidence) AS evidenceRels
   CALL apoc.refactor.mergeRelationships([anchor] + evidenceRels, {properties: 'combine', produceSelfRel: false})
   YIELD rel
   WITH rel, properties(rel) AS props
   WITH rel, apoc.map.fromLists(
       keys(props),
       [k IN keys(props) |
           apoc.coll.toSet([x IN apoc.coll.flatten([props[k]]) WHERE x IS NOT NULL])
       ]
   ) AS uniqueMap
   WITH rel, apoc.map.fromLists(
       keys(uniqueMap),
       [k IN keys(uniqueMap) |
           CASE size(uniqueMap[k])
               WHEN 0 THEN null
               WHEN 1 THEN uniqueMap[k][0]
               ELSE uniqueMap[k]
           END
       ]
   ) AS finalProps
   SET rel = finalProps",

  // 3. CONFIGURATION
  {
    batchSize: 10000,
    parallel: true,
    retries: 3,
    concurrency: 4
  }
)
YIELD committedOperations, failedOperations, errorMessages
RETURN
  "FuncAssocReg2MolSynthesis" AS merge_type,
  committedOperations AS mergedCount,
  failedOperations AS failedCount,
  errorMessages AS errors

UNION

//STEP 21. Merge reversed FunctionalAssociation to MolSynthesis:
//ESTIMATE: CALL { {DRIVING} } WITH anchor WHERE rand() < $p WITH collect(anchor) AS sample UNWIND sample AS anchor WITH sample, startNode(anchor) AS a, endNode(anchor) AS b MATCH (b)-[e:`FunctionalAssociation`]->(a) RETURN size(sample) AS sampleN, count(e) AS merges
// apoc.periodic.iterate: batches of 10000, committed separately; progress is reported by the App.
CALL apoc.periodic.iterate(
  // 1. DRIVING STATEMENT
  "MATCH (a)-[anchor:`MolSynthesis`]->(b) WHERE EXISTS { MATCH (b)-[e:`FunctionalAssociation`]->(a) } RETURN anchor",

  // 2. ACTION STATEMENT
  "WITH anchor, startNode(anchor) AS a, endNode(anchor) AS b
   MATCH (b)-[assoc:`FunctionalAssociation`]->(a)
   WITH anchor, collect(assoc) AS evidence
   WITH anchor, evidence, [rb IN evidence | properties(rb)] AS assoc_props_list
   WITH anchor, evidence, assoc_props_list,
        apoc.coll.toSet(keys(properties(anchor)) + apoc.coll.flatten([m IN assoc_props_list | keys(m)])) AS all_keys
   WITH anchor, evidence,
        apoc.map.fromLists(all_keys, [k IN all_keys |
            apoc.coll.flatten([coalesce(properties(anchor)[k], [])]) +
            apoc.coll.flatten([m IN assoc_props_list | coalesce(m[k], [])])
        ]) AS mergedProps
   SET anchor = mergedProps
   WITH anchor, evidence
   UNWIND evidence AS rb
   DELETE rb",

  // 3. CONFIGURATION
  {
    batchSize: 10000,
    parallel: true,
    retries: 3,
    concurrency: 4
  }
)
YIELD committedOperations, failedOperations, errorMessages
RETURN
  "reversedFuncAssoc2MolSynthesis" AS merge_type,
  committedOperations AS mergedCount,
  failedOperations AS failedCount,
  errorMessages AS errors
