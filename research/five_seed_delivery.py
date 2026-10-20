"""Read-only final result verification; no formatting success substitutes for real data."""
from pathlib import Path
from research.integrity import read_json,digest
from research.five_seed_release import verify_bundle
from research.five_seed_config import DIRECTORIES,SEEDS,STUDY
from research.five_seed_audit import audit


def verify_results(root,directory,bundle_path):
    root=Path(root).resolve();directory=Path(directory).resolve();bundle_path=Path(bundle_path).resolve()
    if not directory.is_relative_to(root/'runs/readiness'):raise ValueError('Unregistered result directory')
    seal=read_json(directory/'analysis_seal.json')
    if seal.get('synthetic') is not False:raise ValueError('Synthetic output is not a study result')
    actual={p.relative_to(directory).as_posix():digest(p) for p in directory.rglob('*')
            if p.is_file() and p.name!='analysis_seal.json'}
    if actual!=seal.get('files'):raise ValueError('Final result membership or bytes changed')
    results=read_json(directory/'results.json')
    if (results.get('study_id')!=STUDY or results.get('synthetic') is not False
            or results.get('seeds')!=list(SEEDS) or results.get('independent_case_count')!=100
            or results.get('case_seed_count')!=500):raise ValueError('Wrong real result scope')
    provenance=results['provenance']
    if provenance!=seal['provenance'] or provenance['bundle_sha256']!=digest(bundle_path):
        raise ValueError('Final result launch provenance changed')
    counts={}
    for phase,expected in [('main',1000),('ablations',2500)]:
        verify_bundle(root,bundle_path,phase=phase)
        report,manifest,_=audit(root/DIRECTORIES[phase])
        if (report['initial_predictions']!=expected or manifest.get('bundle_sha256')!=digest(bundle_path)
                or provenance[phase]['seal_sha256']!=digest(root/DIRECTORIES[phase]/'seal.json')
                or provenance[phase]['manifest_sha256']!=digest(root/DIRECTORIES[phase]/'run_manifest.json')):
            raise ValueError('Results are not tied to the actual main/ablation archives')
        counts[phase]=report['initial_predictions']
    # Recompute statistics from the sealed observations and verified judge
    # receipts. A self-consistent, resealed but fabricated result must fail.
    from research.five_seed_scoring import score
    from research.five_seed_analysis import analyze_records
    main=score(root,bundle_path,'main',root/provenance['judge_directories']['main'])
    ablations=score(root,bundle_path,'ablations',root/provenance['judge_directories']['ablations'])
    recomputed=analyze_records(main['analysis_records']+ablations['analysis_records'])
    if {k:v for k,v in results.items() if k!='provenance'}!=recomputed:
        raise ValueError('Published numerical results do not reproduce from original observations')
    return {'status':'VERIFIED_RESULTS_ARCHIVES_AND_PROVENANCE','initial_predictions':counts,
            'results_sha256':digest(directory/'results.json'),'analysis_seal_sha256':digest(directory/'analysis_seal.json'),
            'semantic_point_estimates_available':all(x['difference'] is not None for x in results['paired_effects'].values()),
            'semantic_truth_guaranteed':False}
