//STEP 1. Merge same type relations:
MATCH (a)-[r]->(b)
WITH a, b, type(r) AS relType, collect(r) AS rels
WHERE size(rels) > 1
// Sort by quality
UNWIND rels AS r
WITH a, b, relType, r
ORDER BY coalesce(r.RelationNumberOfReferences, 0) DESC
WITH a, b, relType, collect(r) AS sortedRels
// Merge into a single survivor
CALL apoc.refactor.mergeRelationships(sortedRels, {properties: ""combine""})
YIELD rel
// Immediate Cleanup
WITH relType, rel, properties(rel) AS props
WITH relType, rel, apoc.map.fromLists(
    keys(props), 
    [k IN keys(props) | 
        // Use apoc.coll.toSet on the filtered list directly
        apoc.coll.toSet([v IN apoc.coll.flatten([props[k]]) WHERE v IS NOT NULL | v])
    ]
) AS uniqueMap
// Unwrap single-item lists to strings
WITH relType, rel, uniqueMap
WITH relType, rel, apoc.map.fromLists(
    keys(uniqueMap),
    [k IN keys(uniqueMap) | 
        CASE 
            WHEN size(uniqueMap[k]) = 0 THEN null
            WHEN size(uniqueMap[k]) = 1 THEN uniqueMap[k][0]
            ELSE uniqueMap[k]
        END
    ]
) AS finalProps
SET rel = finalProps
RETURN "Same reltype" AS merge_type, count(rel) AS mergedCount

UNION

//STEP 2. Merge to Regulation FunctionalAssociation:
MATCH (a)-[anchor:Regulation]->(b)
MATCH (a)-[evidence:FunctionalAssociation]->(b)
WITH a, b, anchor, collect(evidence) AS evidenceRels
// [anchor] + evidenceRels ensures 'anchor' is index 0 and survives
CALL apoc.refactor.mergeRelationships([anchor] + evidenceRels, {
    properties: ""combine"",
    produceSelfRel: false
})
YIELD rel
// Immediate Cleanup
WITH rel, properties(rel) AS props
WITH rel, apoc.map.fromLists(
    keys(props), 
    [k IN keys(props) | 
        // Use apoc.coll.toSet on the filtered list directly
        apoc.coll.toSet([v IN apoc.coll.flatten([props[k]]) WHERE v IS NOT NULL | v])
    ]
) AS uniqueMap
// Final step: Unwrap single-item lists to strings
WITH rel, uniqueMap
WITH rel, apoc.map.fromLists(
    keys(uniqueMap),
    [k IN keys(uniqueMap) | 
        CASE 
            WHEN size(uniqueMap[k]) = 0 THEN null
            WHEN size(uniqueMap[k]) = 1 THEN uniqueMap[k][0]
            ELSE uniqueMap[k]
        END
    ]
) AS finalProps
SET rel = finalProps
RETURN "FuncAssoc2Regulation" AS merge_type, count(rel) AS mergedCount

UNION

//STEP 3. Merge to Regulation reverse FunctionalAssociation:
MATCH (a)-[anchor:Regulation]->(b)
MATCH (b)-[assoc:FunctionalAssociation]->(a)
// Group bindings by anchor to handle multiple bindings per pair
WITH anchor, collect(assoc) AS evidence
WITH anchor, evidence, [rb IN evidence | properties(rb)] AS assoc_props_list
// Extract all unique keys from both the anchor and the reversed bindings
WITH anchor, evidence, assoc_props_list,
     apoc.coll.toSet(keys(properties(anchor)) + apoc.coll.flatten([m IN assoc_props_list | keys(m)])) AS all_keys
// Build the combined property map
WITH anchor, evidence,
     apoc.map.fromLists(all_keys, [k IN all_keys | 
         apoc.coll.flatten([coalesce(properties(anchor)[k], [])]) + 
         apoc.coll.flatten([m IN assoc_props_list | coalesce(m[k], [])])
     ]) AS mergedProps
// Apply the properties to the anchor and delete the reversed relationships
SET anchor = mergedProps
WITH evidence
UNWIND evidence AS rb
DELETE rb
RETURN "reversedFuncAssoc2Regulation" AS merge_type, count(rel) AS mergedCount

UNION

//STEP 4. Create DirectRegulation from >> Binding+Regulation (same direction):
MATCH (a)-[r:Regulation|Binding]->(b)
WHERE r.RelationNumberOfReferences > 1 //>1 ref fosafety
WITH a, b, collect(r) AS rels
WHERE size(rels) > 1

UNWIND rels AS r
WITH a, b, r
ORDER BY coalesce(r.RelationNumberOfReferences, 0) DESC
WITH a, b, collect(r) AS sortedRels
// Use apoc.refactor.create.relationship to build the new type 
// We use the properties of the first (strongest) relation as a base
CALL apoc.create.relationship(a, 'DirectRegulation', properties(sortedRels[0]), b) 
YIELD rel AS newRel
// Merge the properties from the OTHER old relations into the new one
CALL apoc.refactor.mergeRelationships([newRel]+sortedRels, {
    properties: ""combine"",
    produceSelfRel: false
})
YIELD rel
// Immediate Cleanup
WITH rel, properties(rel) AS props
WITH rel, apoc.map.fromLists(
    keys(props), 
    [k IN keys(props) | 
        // Use apoc.coll.toSet on the filtered list directly
        apoc.coll.toSet([v IN apoc.coll.flatten([props[k]]) WHERE v IS NOT NULL | v])
    ]
) AS uniqueMap
// Final step: Unwrap single-item lists to strings
WITH rel, uniqueMap
WITH rel, apoc.map.fromLists(
    keys(uniqueMap),
    [k IN keys(uniqueMap) | 
        CASE 
            WHEN size(uniqueMap[k]) = 0 THEN null
            WHEN size(uniqueMap[k]) = 1 THEN uniqueMap[k][0]
            ELSE uniqueMap[k]
        END
    ]
) AS finalProps

SET rel = finalProps
RETURN "createDirectRegulation" AS merge_type, count(rel) AS mergedCount

UNION

//STEP 5. Create DirectRegulation from >< Bind+Regulation (opposite_direction):
// Find Anchor Regulation (A -> B) and Reversed Bindings (B -> A)
MATCH (a)-[reg:Regulation]->(b)
MATCH (b)-[bind:Binding]->(a)
WHERE bind.RelationNumberOfReferences > 2
// Group them
WITH a, b, collect(reg) AS regs, collect(bind) AS rev_binds
// Combine all property maps
WITH a, b, regs, rev_binds, 
     [r IN regs + rev_binds | properties(r)] AS all_props_maps
// Extract unique property names
WITH a, b, regs, rev_binds, all_props_maps,
     apoc.coll.toSet(apoc.coll.flatten([m IN all_props_maps | keys(m)])) AS all_keys
// Build the property map
WITH a, b, regs, rev_binds,
     apoc.map.fromLists(all_keys, [k IN all_keys | 
        apoc.coll.flatten([m IN all_props_maps | coalesce(m[k], [])])
     ]) AS combinedProps
// Create the new Directed relationship
CALL apoc.create.relationship(a, 'DirectRegulation', combinedProps, b) 
YIELD rel AS newRel
// Delete original evidence
WITH regs, rev_binds, newRel
FOREACH (r IN regs | DELETE r)
FOREACH (rb IN rev_binds | DELETE rb)
// Final Cleanup (Deduplicate)
WITH newRel, properties(newRel) AS props
WITH newRel, apoc.map.fromLists(
    keys(props), 
    [k IN keys(props) | 
    [val IN apoc.coll.flatten([props[k]]) 
         WHERE val IS NOT NULL | val]
    ]
) AS filteredLists

WITH newRel, apoc.map.fromLists(
    keys(filteredLists),
    [k IN keys(filteredLists) | 
        WITH apoc.coll.toSet(filteredLists[k]) AS uniqueVals
        RETURN 
        CASE 
            WHEN size(uniqueVals) = 0 THEN null
            WHEN size(uniqueVals) = 1 THEN uniqueVals[0]
            ELSE uniqueVals
        END
    ]
) AS finalProps
SET newRel = finalProps
RETURN "createDirectRegulationReversedBinding" AS merge_type, count(rel) AS mergedCount

UNION

//STEP 6. Merge same type relations:
MATCH (a)-[r]->(b)
WITH a, b, type(r) AS relType, collect(r) AS rels
WHERE size(rels) > 1
// Sort by references
UNWIND rels AS r
WITH a, b, relType, r
ORDER BY coalesce(r.RelationNumberOfReferences, 0) DESC
WITH a, b, relType, collect(r) AS sortedRels
// Perform the merge
CALL apoc.refactor.mergeRelationships(sortedRels, {properties: ""combine""})
YIELD rel
// Immediate Cleanup
WITH relType, rel, properties(rel) AS props
WITH relType, rel, apoc.map.fromLists(
    keys(props), 
    [k IN keys(props) | 
        // Use apoc.coll.toSet on the filtered list directly
        apoc.coll.toSet([v IN apoc.coll.flatten([props[k]]) WHERE v IS NOT NULL | v])
    ]
) AS uniqueMap
// Final step: Unwrap single-item lists to strings
WITH relType, rel, uniqueMap
WITH relType, rel, apoc.map.fromLists(
    keys(uniqueMap),
    [k IN keys(uniqueMap) | 
        CASE 
            WHEN size(uniqueMap[k]) = 0 THEN null
            WHEN size(uniqueMap[k]) = 1 THEN uniqueMap[k][0]
            ELSE uniqueMap[k]
        END
    ]
) AS finalProps
SET rel = finalProps
RETURN "Same reltype after DirectReglation" AS merge_type, count(rel) AS mergedCount

UNION

//STEP 7. Convert ProtModification to Regulation for non-enzymes:
// Identify all enzymes including their sub-classes via the is_a hierarchy
MATCH (p)
WHERE p.Name IN [
    'protein kinase', 'acetyltransferase', 'peptide hydrolase',
    'deacetylase', 'protein methyltransferase', 'histone modification enzyme',
    'aminoacyltransferase', 'peptide synthase', 'protein phosphatase'
]
OPTIONAL MATCH (child)-[:is_a*]->(p)
WITH collect(DISTINCT child) + collect(DISTINCT p) AS enzymeNodes
// Find ProtModification relations where the regulator (n) is NOT in that list
MATCH (n)-[r:ProtModification]->(t)
WHERE NOT n IN enzymeNodes
// Change the relationship type to 'Regulation'
CALL apoc.refactor.setType(r, 'Regulation') 
YIELD input, output
// Return the results
RETURN "ConvertProtMod2Regulation" AS merge_type, count(rel) AS mergedCount

UNION

//STEP 8. Merge to ProtModification [Regulation]:
// Identify Enzyme nodes (Parents + Children)
MATCH (p)
WHERE p.Name IN [
    'protein kinase', 'acetyltransferase', 'peptide hydrolase',
    'deacetylase', 'protein methyltransferase', 'histone modification enzyme',
    'aminoacyltransferase', 'peptide synthase', 'protein phosphatase'
]
OPTIONAL MATCH (child)-[:is_a*]->(p)
WITH collect(DISTINCT p) + collect(DISTINCT child) AS all_enzymes
// Match pairs connected by BOTH types in the same direction
UNWIND all_enzymes AS enzyme
MATCH (enzyme)-[r1:ProtModification]->(b)
MATCH (enzyme)-[r2:Regulation]->(b)
// Group all relationships between this specific pair
WITH enzyme, b, collect(DISTINCT r1) + collect(DISTINCT r2) AS rels
// Sort: Priority to ProtModification as the 'Survivor'
UNWIND rels AS r
WITH enzyme, b, r
ORDER BY 
  CASE type(r) 
    WHEN 'ProtModification' THEN 1 
    WHEN 'Regulation' THEN 2 
  END ASC, 
  coalesce(r.RelationNumberOfReferences, 0) DESC
WITH enzyme, b, collect(r) AS sortedRels
// Merge (The first rel in sortedRels will be the survivor)
CALL apoc.refactor.mergeRelationships(sortedRels, {properties: ""combine""})
YIELD rel
// Cleanup Logic (Unique values, preserve ""_"")
WITH rel, properties(rel) AS props
WITH rel, apoc.map.fromLists(
    keys(props), 
    [k IN keys(props) | 
        apoc.coll.toSet([v IN apoc.coll.flatten([props[k]]) WHERE v IS NOT NULL | v])
    ]
) AS uniqueMap
WITH rel, uniqueMap
WITH rel, apoc.map.fromLists(
    keys(uniqueMap),
    [k IN keys(uniqueMap) | 
        CASE 
            WHEN size(uniqueMap[k]) = 0 THEN null
            WHEN size(uniqueMap[k]) = 1 THEN uniqueMap[k][0]
            ELSE uniqueMap[k]
        END
    ]
) AS finalProps
SET rel = finalProps
RETURN "Regulation2ProtMod" AS merge_type, count(rel) AS mergedCount

UNION

//STEP 9. Merge to DirectRegulation [Regulation|Binding|ProtModification]:
MATCH (a)-[anchor:DirectRegulation]->(b)
MATCH (a)-[evidence:Regulation|Binding|ProtModification]->(b)
WITH a, b, anchor, collect(evidence) AS evidenceRels
// Merge evidence into the existing anchor
// [anchor] + evidenceRels ensures 'anchor' is index 0 and survives
CALL apoc.refactor.mergeRelationships([anchor] + evidenceRels, {
    properties: ""combine"",
    produceSelfRel: false
})
YIELD rel
// Immediate Cleanup
WITH rel, properties(rel) AS props
WITH rel, apoc.map.fromLists(
    keys(props), 
    [k IN keys(props) | 
        // Use apoc.coll.toSet on the filtered list directly
        apoc.coll.toSet([v IN apoc.coll.flatten([props[k]]) WHERE v IS NOT NULL | v])
    ]
) AS uniqueMap
// Final step: Unwrap single-item lists to strings
WITH rel, uniqueMap
WITH rel, apoc.map.fromLists(
    keys(uniqueMap),
    [k IN keys(uniqueMap) | 
        CASE 
            WHEN size(uniqueMap[k]) = 0 THEN null
            WHEN size(uniqueMap[k]) = 1 THEN uniqueMap[k][0]
            ELSE uniqueMap[k]
        END
    ]
) AS finalProps
SET rel = finalProps
RETURN "RegProtModBind2DirectRegulation" AS merge_type, count(rel) AS mergedCount

UNION

//STEP 10. Merge to DirectRegulation [reverse Binding]:
MATCH (a)-[anchor:DirectRegulation]->(b)
MATCH (b)-[bind:Binding]->(a)
WHERE bind.RelationNumberOfReferences > 2
// Group bindings by anchor to handle multiple bindings per pair
WITH anchor, collect(bind) AS rev_binds
WITH anchor, rev_binds, [rb IN rev_binds | properties(rb)] AS bind_props_list
// Extract all unique keys from both the anchor and the reversed bindings
WITH anchor, rev_binds, bind_props_list,
     apoc.coll.toSet(keys(properties(anchor)) + apoc.coll.flatten([m IN bind_props_list | keys(m)])) AS all_keys
// Build the combined property map
WITH anchor, rev_binds,
     apoc.map.fromLists(all_keys, [k IN all_keys | 
         apoc.coll.flatten([coalesce(properties(anchor)[k], [])]) + 
         apoc.coll.flatten([m IN bind_props_list | coalesce(m[k], [])])
     ]) AS mergedProps
// Apply the properties to the anchor and delete the reversed relationships
SET anchor = mergedProps
WITH rev_binds
UNWIND rev_binds AS rb
DELETE rb
RETURN "reversedBind2DirectRegulation" AS merge_type, count(rel) AS mergedCount

UNION

//STEP 11. Merge to Expression [Regulation.FunctionalAssociation]:
MATCH (a)-[anchor:Expression]->(b)
MATCH (a)-[evidence:Regulation|FunctionalAssociation]->(b)
WITH a, b, anchor, collect(evidence) AS evidenceRels
// Merge evidence into the existing anchor:
// [anchor] + evidenceRels ensures 'anchor' is index 0 and survives
CALL apoc.refactor.mergeRelationships([anchor] + evidenceRels, {
    properties: ""combine"",
    produceSelfRel: false
})
YIELD rel
// Immediate Cleanup
WITH rel, properties(rel) AS props
WITH rel, apoc.map.fromLists(
    keys(props), 
    [k IN keys(props) | 
        // Use apoc.coll.toSet on the filtered list directly
        apoc.coll.toSet([v IN apoc.coll.flatten([props[k]]) WHERE v IS NOT NULL | v])
    ]
) AS uniqueMap
// Final step: Unwrap single-item lists to strings
WITH rel, uniqueMap
WITH rel, apoc.map.fromLists(
    keys(uniqueMap),
    [k IN keys(uniqueMap) | 
        CASE 
            WHEN size(uniqueMap[k]) = 0 THEN null
            WHEN size(uniqueMap[k]) = 1 THEN uniqueMap[k][0]
            ELSE uniqueMap[k]
        END
    ]
) AS finalProps
SET rel = finalProps
RETURN "RegFuncAssoc2Expression" AS merge_type, count(rel) AS mergedCount

UNION

//STEP 12. Merge to Expression reverse FunctionalAssociation
MATCH (a)-[anchor:Expression]->(b)
MATCH (b)-[assoc:FunctionalAssociation]->(a)
// Group bindings by anchor to handle multiple bindings per pair
WITH anchor, collect(assoc) AS evidence
WITH anchor, evidence, [rb IN evidence | properties(rb)] AS assoc_props_list
// Extract all unique keys from both the anchor and the reversed bindings
WITH anchor, evidence, assoc_props_list,
     apoc.coll.toSet(keys(properties(anchor)) + apoc.coll.flatten([m IN assoc_props_list | keys(m)])) AS all_keys
// Build the combined property map
WITH anchor, evidence,
     apoc.map.fromLists(all_keys, [k IN all_keys | 
         apoc.coll.flatten([coalesce(properties(anchor)[k], [])]) + 
         apoc.coll.flatten([m IN assoc_props_list | coalesce(m[k], [])])
     ]) AS mergedProps
// Apply the properties to the anchor and delete the reversed relationships
SET anchor = mergedProps
WITH evidence
UNWIND evidence AS rb
DELETE rb
RETURN "reversedFuncAssoc2Expression" AS merge_type, count(rel) AS mergedCount

UNION

//STEP 13. Merge to PromoterBinding [Regulation,Expression]:
MATCH (a)-[anchor:PromoterBinding]->(b)
MATCH (a)-[evidence:Regulation|Expression]->(b)
WITH a, b, anchor, collect(evidence) AS evidenceRels
// Merge evidence into the existing anchor
// [anchor] + evidenceRels ensures 'anchor' is index 0 and survives
CALL apoc.refactor.mergeRelationships([anchor] + evidenceRels, {
    properties: ""combine"",
    produceSelfRel: false
})
YIELD rel
RETURN "RegExpr2PromoterBinding" AS merge_type, count(rel) AS mergedCount

UNION

//STEP 14. Merge to QuantitativeChange FunctionalAssociation
MATCH (a)-[anchor:QuantitativeChange]->(b)
MATCH (a)-[evidence:FunctionalAssociation]->(b)
WITH a, b, anchor, collect(evidence) AS evidenceRels
// Merge evidence into the existing anchor
// [anchor] + evidenceRels ensures 'anchor' is index 0 and survives
CALL apoc.refactor.mergeRelationships([anchor] + evidenceRels, {properties:""combine"", produceSelfRel:false})
YIELD rel
RETURN "FuncAssoc2QuantitativeChange" AS merge_type, count(rel) AS mergedCount

UNION

//STEP 16. Merge to QuantitativeChange reverse FunctionalAssociation
MATCH (a)-[anchor:QuantitativeChange]->(b)
MATCH (b)-[assoc:FunctionalAssociation]->(a)
// Group bindings by anchor to handle multiple bindings per pair
WITH anchor, collect(assoc) AS evidence
WITH anchor, evidence, [rb IN evidence | properties(rb)] AS assoc_props_list
// Extract all unique keys from both the anchor and the reversed bindings
WITH anchor, evidence, assoc_props_list,
     apoc.coll.toSet(keys(properties(anchor)) + apoc.coll.flatten([m IN assoc_props_list | keys(m)])) AS all_keys
// Build the combined property map
WITH anchor, evidence,
     apoc.map.fromLists(all_keys, [k IN all_keys | 
         apoc.coll.flatten([coalesce(properties(anchor)[k], [])]) + 
         apoc.coll.flatten([m IN assoc_props_list | coalesce(m[k], [])])
     ]) AS mergedProps
// Apply the properties to the anchor and delete the reversed relationships
SET anchor = mergedProps
WITH evidence
UNWIND evidence AS rb
DELETE rb
RETURN "reversedFuncAssoc2QuantitativeChange" AS merge_type, count(rel) AS mergedCount

UNION

//STEP 17. Merge to Biomarker [QuantitativeChange, FunctionalAssociation]:
MATCH (a)-[anchor:Biomarker]->(b)
MATCH (a)-[evidence:QuantitativeChange|FunctionalAssociation]->(b)
WITH a, b, anchor, collect(evidence) AS evidenceRels
// Merge evidence into the existing anchor
// [anchor] + evidenceRels ensures 'anchor' is index 0 and survives
CALL apoc.refactor.mergeRelationships([anchor] + evidenceRels, {
    properties: ""combine"",
    produceSelfRel: false
})
YIELD rel
RETURN "QuanChangeFuncAssoc2Biomarker" AS merge_type, count(rel) AS mergedCount

UNION

//STEP 18. Merge to Biomarker reverse FunctionalAssociation:
MATCH (a)-[anchor:Biomarker]->(b)
MATCH (b)-[assoc:FunctionalAssociation]->(a)
// Group bindings by anchor to handle multiple bindings per pair
WITH anchor, collect(assoc) AS evidence
WITH anchor, evidence, [rb IN evidence | properties(rb)] AS assoc_props_list
// Extract all unique keys from both the anchor and the reversed bindings
WITH anchor, evidence, assoc_props_list,
     apoc.coll.toSet(keys(properties(anchor)) + apoc.coll.flatten([m IN assoc_props_list | keys(m)])) AS all_keys
// Build the combined property map
WITH anchor, evidence,
     apoc.map.fromLists(all_keys, [k IN all_keys | 
         apoc.coll.flatten([coalesce(properties(anchor)[k], [])]) + 
         apoc.coll.flatten([m IN assoc_props_list | coalesce(m[k], [])])
     ]) AS mergedProps
// Apply the properties to the anchor and delete the reversed relationships
SET anchor = mergedProps
WITH evidence
UNWIND evidence AS rb
DELETE rb
RETURN "reversedFuncAssoc2Biomarker" AS merge_type, count(rel) AS mergedCount

UNION

//STEP 19. Merge to Moltransport [Regulation,CellExpression,FunctionalAssociation]:
MATCH (a)-[anchor:MolTransport]->(b)
MATCH (a)-[evidence:CellExpression|Regulation|FunctionalAssociation]->(b)
WITH a, b, anchor, collect(evidence) AS evidenceRels
// Merge evidence into the existing anchor
// [anchor] + evidenceRels ensures 'anchor' is index 0 and survives
CALL apoc.refactor.mergeRelationships([anchor] + evidenceRels, {
    properties: ""combine"",
    produceSelfRel: false
})
YIELD rel
// Immediate Cleanup
WITH rel, properties(rel) AS props
WITH rel, apoc.map.fromLists(
    keys(props), 
    [k IN keys(props) | 
        // Use apoc.coll.toSet on the filtered list directly
        apoc.coll.toSet([v IN apoc.coll.flatten([props[k]]) WHERE v IS NOT NULL | v])
    ]
) AS uniqueMap
// Final step: Unwrap single-item lists to strings
WITH rel, uniqueMap
WITH rel, apoc.map.fromLists(
    keys(uniqueMap),
    [k IN keys(uniqueMap) | 
        CASE 
            WHEN size(uniqueMap[k]) = 0 THEN null
            WHEN size(uniqueMap[k]) = 1 THEN uniqueMap[k][0]
            ELSE uniqueMap[k]
        END
    ]
) AS finalProps
SET rel = finalProps
RETURN "FuncAssocCellExpReg2MolTransport" AS merge_type, count(rel) AS mergedCount

UNION

//STEP 20. Merge to MolTransport reverse CellExpression,FunctionalAssociation:
MATCH (a)-[anchor:MolTransport]->(b)
MATCH (b)-[assoc:FunctionalAssociation|CellExpression]->(a)
// Group bindings by anchor to handle multiple bindings per pair
WITH anchor, collect(assoc) AS evidence
WITH anchor, evidence, [rb IN evidence | properties(rb)] AS assoc_props_list
// Extract all unique keys from both the anchor and the reversed bindings
WITH anchor, evidence, assoc_props_list,
     apoc.coll.toSet(keys(properties(anchor)) + apoc.coll.flatten([m IN assoc_props_list | keys(m)])) AS all_keys
// Build the combined property map
WITH anchor, evidence,
     apoc.map.fromLists(all_keys, [k IN all_keys | 
         apoc.coll.flatten([coalesce(properties(anchor)[k], [])]) + 
         apoc.coll.flatten([m IN assoc_props_list | coalesce(m[k], [])])
     ]) AS mergedProps
// Apply the properties to the anchor and delete the reversed relationships
SET anchor = mergedProps
WITH evidence
UNWIND evidence AS rb
DELETE rb
RETURN "reversedFuncAssocCellExp2MolTransport" AS merge_type, count(rel) AS mergedCount

UNION

//STEP 21. Merge to MolSynthesis [Regulation.FunctionalAssociation]:
MATCH (a)-[anchor:MolSynthesis]->(b)
MATCH (a)-[evidence:Regulation|FunctionalAssociation]->(b)
WITH a, b, anchor, collect(evidence) AS evidenceRels
// Merge evidence into the existing anchor
// [anchor] + evidenceRels ensures 'anchor' is index 0 and survives
CALL apoc.refactor.mergeRelationships([anchor] + evidenceRels, {
    properties: ""combine"",
    produceSelfRel: false
})
YIELD rel
// Immediate Cleanup
WITH rel, properties(rel) AS props
WITH rel, apoc.map.fromLists(
    keys(props), 
    [k IN keys(props) | 
        // Use apoc.coll.toSet on the filtered list directly
        apoc.coll.toSet([v IN apoc.coll.flatten([props[k]]) WHERE v IS NOT NULL | v])
    ]
) AS uniqueMap
// Final step: Unwrap single-item lists to strings
WITH rel, uniqueMap
WITH rel, apoc.map.fromLists(
    keys(uniqueMap),
    [k IN keys(uniqueMap) | 
        CASE 
            WHEN size(uniqueMap[k]) = 0 THEN null
            WHEN size(uniqueMap[k]) = 1 THEN uniqueMap[k][0]
            ELSE uniqueMap[k]
        END
    ]
) AS finalProps
SET rel = finalProps
RETURN "FuncAssocReg2MolSynthesis" AS merge_type, count(rel) AS mergedCount

UNION

//STEP 22. Merge to MolSynthesis reverse FunctionalAssociation:
MATCH (a)-[anchor:MolSynthesis]->(b)
MATCH (b)-[assoc:FunctionalAssociation]->(a)
// Group bindings by anchor to handle multiple bindings per pair
WITH anchor, collect(assoc) AS evidence
WITH anchor, evidence, [rb IN evidence | properties(rb)] AS assoc_props_list
// Extract all unique keys from both the anchor and the reversed bindings
WITH anchor, evidence, assoc_props_list,
     apoc.coll.toSet(keys(properties(anchor)) + apoc.coll.flatten([m IN assoc_props_list | keys(m)])) AS all_keys
// Build the combined property map
WITH anchor, evidence,
     apoc.map.fromLists(all_keys, [k IN all_keys | 
         apoc.coll.flatten([coalesce(properties(anchor)[k], [])]) + 
         apoc.coll.flatten([m IN assoc_props_list | coalesce(m[k], [])])
     ]) AS mergedProps
// Apply the properties to the anchor and delete the reversed relationships
SET anchor = mergedProps
WITH evidence
UNWIND evidence AS rb
DELETE rb
RETURN "reversedFuncAssoc2MolSynthesis " AS merge_type, count(rel) AS mergedCount