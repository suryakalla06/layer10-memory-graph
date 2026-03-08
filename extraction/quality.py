def passes_quality_gate(claim):
    # Ensure claim has subject/object
    if not claim.subject_id or not claim.object_id:
        return False
        
    # Must have at least one piece of evidence
    if not claim.evidence:
        return False
        
    # Ensure evidence is properly grounded with a source ID
    if not any(ev.source_id for ev in claim.evidence):
        return False
        
    return True