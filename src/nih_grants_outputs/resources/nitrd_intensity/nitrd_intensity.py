"""Deterministic, exploratory NITRD output-intensity scorer. Python 3.10+.

No network calls, third-party dependencies, MCP, or fitted model. Read DESIGN.md
before using scores. Rules are hypotheses, not validated NITRD classifications.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import re
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any

PCAS = ('LSDMA', 'HCIA', 'CHuman', 'AI', 'EHCS', 'CSP', 'SPSQ')
TARGETS = ('overall', *PCAS)
VERSION = '0.1.0'


def canonical_json(value: Any) -> bytes:
    """Hash representation: sorted keys, UTF-8, compact separators, no NaN."""
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def normalize(value: str) -> str:
    value = unicodedata.normalize('NFKC', value).casefold()
    return re.sub(r'[^\w]+', ' ', value, flags=re.UNICODE).strip()


def normalize_doi(value: str | None) -> str | None:
    if not value:
        return None
    if not isinstance(value, str):
        raise ValueError('DOI must be a string or null.')
    value = re.sub(r'^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)', '',
                   value.strip(), flags=re.I).casefold()
    if not re.fullmatch(r'10\.\d{4,9}/\S+', value):
        raise ValueError(f'Malformed DOI: {value!r}; resolve it upstream.')
    return value


def _unit_interval(value: Any) -> bool:
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and 0 <= value <= 1)


def load_config(path: str | Path | None = None) -> dict:
    path = Path(path) if path else Path(__file__).with_name('rules.json')
    config = json.loads(path.read_text(encoding='utf-8'))
    validate_config(config)
    return config


def validate_config(config: dict) -> None:
    if config.get('schema_version') != 1 or config.get('pcas') != list(PCAS):
        raise ValueError('Expected schema_version=1 and the seven configured PCAs.')
    required = {'publication': {'mesh', 'title', 'venue'},
                'datacite': {'title', 'resource_type'}}
    if set(config['signal_weights']) != set(required):
        raise ValueError('Invalid signal-weight streams.')
    for kind, expected in required.items():
        weights = config['signal_weights'][kind]
        if (set(weights) != expected or not all(_unit_interval(v) for v in weights.values())
                or not math.isclose(sum(weights.values()), 1.0, abs_tol=1e-12)):
            raise ValueError(f'{kind} signal weights must be nonnegative and sum to one.')
    weights = config['stream_weights']
    if (set(weights) != set(required) or not all(_unit_interval(v) for v in weights.values())
            or not math.isclose(sum(weights.values()), 1.0, abs_tol=1e-12)):
        raise ValueError('Stream weights must be nonnegative and sum to one.')
    for name in ('resource_types', 'publication_type_factors'):
        if not all(_unit_interval(v) for v in config[name].values()):
            raise ValueError(f'Invalid values in {name}.')
    for family in ('mesh', 'title_rules'):
        seen = set()
        for rule in config[family]:
            if rule['id'] in seen:
                raise ValueError(f'Duplicate {family} rule: {rule["id"]}')
            seen.add(rule['id'])
            if (not _unit_interval(rule['overall'])
                    or any(p not in PCAS or not _unit_interval(v)
                           or v > rule['overall'] for p, v in rule['pca'].items())):
                raise ValueError(f'Invalid affinities: {rule["id"]}')
            if not set(rule.get('title_context_required', [])).issubset(rule['pca']):
                raise ValueError('Context gates must name an affinity in the rule.')
            if family == 'title_rules':
                compiled = re.compile(r'\b(?:' + rule['pattern'] + r')\b')
                if compiled.search(''):
                    raise ValueError('Title expressions cannot match empty strings.')
    # Prevent conflicting aliases from silently overwriting one another.
    aliases = {}
    for rule in config['mesh']:
        for name in [rule['label'], *rule['aliases']]:
            key = normalize(name)
            if key in aliases and aliases[key] != rule['id']:
                raise ValueError(f'Ambiguous MeSH alias: {name}')
            aliases[key] = rule['id']
    names = set()
    for venue in config['venues']:
        if not _unit_interval(venue['strength']):
            raise ValueError('Invalid venue strength.')
        for name in venue['names']:
            key = normalize(name)
            if key in names:
                raise ValueError(f'Duplicate venue alias: {name}')
            names.add(key)


def _text(value: Any, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f'{field} must be a string or null.')
    return value.strip() or None


def _string_list(value: Any, field: str) -> list[str] | None:
    if value is None:
        return None
    if not isinstance(value, list) or any(not isinstance(x, str) or not x.strip() for x in value):
        raise ValueError(f'{field} must be a list of nonempty strings or null.')
    return sorted(set(x.strip() for x in value))


def _record(raw: dict, kind: str) -> dict:
    """Accept enriched iCite dicts and raw DataCite JSON:API or flat dicts."""
    if not isinstance(raw, dict):
        raise ValueError('Each output must be an object.')
    body = raw.get('attributes', raw) if kind == 'datacite' else raw
    if not isinstance(body, dict):
        raise ValueError('DataCite attributes must be an object.')
    pmid = raw.get('pmid')
    if pmid is not None:
        if isinstance(pmid, bool) or not re.fullmatch(r'[1-9]\d*', str(pmid)):
            raise ValueError('PMID must be a positive integer or digit string.')
        pmid = str(pmid)
    doi = normalize_doi(body.get('doi', raw.get('doi')))
    if not doi and kind == 'datacite' and str(raw.get('id', '')).lower().startswith('10.'):
        doi = normalize_doi(raw['id'])
    record_id = _text(raw.get('id'), 'id') or (f'pmid:{pmid}' if pmid else None) or doi
    if record_id is None:
        raise ValueError('Supply a stable id, PMID, or DOI for every record.')
    title = _text(body.get('title'), 'title')
    if title is None and 'titles' in body:
        titles = body['titles']
        if not isinstance(titles, list) or any(not isinstance(t, dict) for t in titles):
            raise ValueError('DataCite titles must be a list of objects.')
        # First primary title in source order; never choose a title by its score.
        candidates = [t for t in titles if not t.get('titleType')] or titles
        title = _text(candidates[0].get('title'), 'titles.title') if candidates else None
    types = body.get('types') or {}
    if not isinstance(types, dict):
        raise ValueError('DataCite types must be an object.')
    resource_type = _text(body.get('resource_type', types.get('resourceTypeGeneral')),
                          'resource_type')
    mesh = raw.get('mesh_terms') if kind == 'publication' else None
    if mesh is not None:
        if not isinstance(mesh, list):
            raise ValueError('mesh_terms must be a list or null.')
        for term in mesh:
            if isinstance(term, str):
                if not term.strip():
                    raise ValueError('Empty MeSH term.')
            elif isinstance(term, dict):
                if not (term.get('ui') or term.get('label')):
                    raise ValueError('MeSH object needs ui or label.')
                for key in ('ui', 'label'):
                    _text(term.get(key), f'mesh_terms.{key}')
            else:
                raise ValueError('MeSH terms must be strings or {ui, label} objects.')
    publication_types = _string_list(raw.get('publication_types'), 'publication_types')
    journal = _text(raw.get('journal', raw.get('journalNameIso')), 'journal') if kind == 'publication' else None
    return dict(record_key=f'{kind}:{record_id}', id=record_id, kind=kind,
                doi=doi, pmid=pmid, work_id=_text(raw.get('work_id'), 'work_id'),
                title=title, mesh_terms=mesh, journal=journal,
                publication_types=publication_types, resource_type=resource_type,
                provenance=copy.deepcopy(raw.get('provenance', {})))


def _deduplicate(records: list[dict]) -> tuple[list[dict], list[dict]]:
    """Transitive identity by DOI, PMID, caller work_id, or source record ID.

    work_id is a caller-verified same-work/version-family identifier. A paper
    describing a dataset is not the same work as the dataset. A reference or
    IsSupplementTo link must not be supplied as work_id.
    """
    parents = list(range(len(records)))

    def root(i: int) -> int:
        while parents[i] != i:
            parents[i] = parents[parents[i]]
            i = parents[i]
        return i

    owners = {}
    for i, record in enumerate(records):
        keys = [('record', record['record_key'])]
        keys += [(field, record[field]) for field in ('doi', 'pmid', 'work_id') if record[field]]
        for key in keys:
            if key in owners:
                parents[root(i)] = root(owners[key])
            else:
                owners[key] = i
    groups = defaultdict(list)
    for i, record in enumerate(records):
        groups[root(i)].append(record)

    def rank(record: dict) -> tuple:
        fields = ('title', 'journal', 'mesh_terms', 'publication_types', 'resource_type')
        # Prefer the publication representation, then field completeness, then
        # stable ID/content hash. Never select by the resulting intensity.
        return (record['kind'] != 'publication',
                -sum(record[k] is not None for k in fields),
                record['record_key'], digest(record))

    unique, report = [], []
    for group in groups.values():
        ordered = sorted(group, key=rank)
        # Different identifiers can legitimately be versions of one work only
        # when the caller has explicitly supplied that verified family identity.
        families = {r['work_id'] for r in group if r['work_id']}
        for identifier in ('doi', 'pmid'):
            identifiers = {r[identifier] for r in group if r[identifier]}
            if len(identifiers) > 1 and not families:
                raise ValueError(f'Conflicting {identifier} values in duplicate group; resolve upstream.')
        chosen = copy.deepcopy(ordered[0])
        chosen['source_records'] = [copy.deepcopy(r) for r in ordered]
        # A richer record must never conceal a retraction or correction flag.
        known_types = [r['publication_types'] for r in ordered if r['publication_types'] is not None]
        if known_types:
            chosen['publication_types'] = sorted(set().union(*map(set, known_types)))
        chosen['work_key'] = min(r['record_key'] for r in ordered)
        if len(group) > 1:
            conflicting = [f for f in ('title', 'journal', 'mesh_terms', 'resource_type')
                           if len({digest(r[f]) for r in group if r[f] is not None}) > 1]
            report.append(dict(work_key=chosen['work_key'], selected=chosen['record_key'],
                               records=[r['record_key'] for r in ordered],
                               conflicts=conflicting,
                               rule='publication_then_field_completeness_then_stable_id'))
        unique.append(chosen)
    return sorted(unique, key=lambda r: r['work_key']), sorted(report, key=lambda r: r['work_key'])


class Scorer:
    def __init__(self, config: dict | None = None):
        self.config = copy.deepcopy(load_config() if config is None else config)
        validate_config(self.config)
        self.by_ui = {r['id']: r for r in self.config['mesh']}
        self.by_label = {}
        for rule in self.config['mesh']:
            for label in [rule['label'], *rule['aliases']]:
                self.by_label[normalize(label)] = rule
        self.titles = [(r, re.compile(r'\b(?:' + r['pattern'] + r')\b'))
                       for r in self.config['title_rules']]
        self.venues = {normalize(name): r for r in self.config['venues'] for name in r['names']}
        self.resources = {normalize(k): v for k, v in self.config['resource_types'].items()}

    def _mesh_rule(self, term: str | dict) -> dict | None:
        if isinstance(term, str):
            # Strip PubMed qualifier and major-topic asterisk, not substrings.
            label = term.split('/', 1)[0].strip().strip('*')
            return self.by_ui.get(term) or self.by_label.get(normalize(label))
        ui = term.get('ui')
        label = term.get('label')
        from_ui = self.by_ui.get(ui) if ui else None
        from_label = self.by_label.get(normalize(label)) if label else None
        if ui and from_label and ui != from_label['id']:
            raise ValueError(f'MeSH UI/label disagreement: {ui!r}, {label!r}')
        if from_ui and label and normalize(label) not in {
                normalize(v) for v in [from_ui['label'], *from_ui['aliases']]}:
            raise ValueError(f'MeSH UI/label disagreement: {ui!r}, {label!r}')
        return from_ui if ui else from_label

    def _score_output(self, record: dict) -> dict:
        kind = record['kind']
        weights = self.config['signal_weights'][kind]
        matches = {family: [] for family in weights}
        unmatched_mesh = []
        title_text = normalize(record['title'] or '')
        for rule, pattern in self.titles:
            found = pattern.search(title_text)
            if found:
                matches['title'].append(dict(rule_id=rule['id'], matched=found.group(0),
                                             overall=rule['overall'], **rule['pca']))
        title_strength = {p: max((m.get(p, 0) for m in matches['title']), default=0.0)
                          for p in TARGETS}
        if kind == 'publication':
            for term in record['mesh_terms'] or []:
                rule = self._mesh_rule(term)
                if rule is None:
                    unmatched_mesh.append(term)
                    continue
                affinity = dict(rule['pca'])
                gates = {}
                for pca in rule.get('title_context_required', []):
                    gates[pca] = title_strength[pca] > 0
                    if not gates[pca]:
                        affinity[pca] = 0.0
                matches['mesh'].append(dict(rule_id=rule['id'], matched=term,
                                            label=rule['label'], source_url=rule['source_url'],
                                            title_context_passed=gates,
                                            overall=rule['overall'], **affinity))
            venue = self.venues.get(normalize(record['journal'] or ''))
            if venue:
                affinity = {}
                for pca in PCAS:
                    mesh_strength = max((m.get(pca, 0) for m in matches['mesh']), default=0.0)
                    affinity[pca] = venue['strength'] * max(mesh_strength, title_strength[pca])
                matches['venue'].append(dict(rule_id=venue['id'], matched=record['journal'],
                                             source_url=venue['source_url'],
                                             overall=venue['strength'], **affinity))
        else:
            resource = normalize(record['resource_type'] or '')
            resource_strength = self.resources.get(resource, 0.0)
            if record['resource_type']:
                matches['resource_type'].append(dict(
                    rule_id='resource:' + resource, matched=record['resource_type'],
                    overall=resource_strength,
                    **{p: resource_strength * title_strength[p] for p in PCAS}))

        pt = {normalize(p) for p in record['publication_types'] or []}
        excluded_types = set(map(normalize, self.config['excluded_publication_types']))
        excluded = sorted(pt & excluded_types)
        factors = {normalize(k): v for k, v in self.config['publication_type_factors'].items()}
        modifier_matches = {p: factors[p] for p in sorted(pt & factors.keys())}
        modifier = min(modifier_matches.values(), default=1.0) if kind == 'publication' else 1.0
        available = {'title': record['title'] is not None}
        if kind == 'publication':
            available.update(mesh=record['mesh_terms'] is not None, venue=record['journal'] is not None)
        else:
            available['resource_type'] = record['resource_type'] is not None
        eligibility = 'eligible'
        if excluded:
            eligibility = 'excluded_publication_type'
        elif not any(available.values()):
            eligibility = 'no_metadata'
        # Deduplicate aliases and repeated input terms before allocating credit.
        for family in matches:
            unique_matches = {}
            for m in matches[family]:
                key = m['rule_id']
                if key not in unique_matches or digest(m) < digest(unique_matches[key]):
                    unique_matches[key] = m
            matches[family] = [unique_matches[k] for k in sorted(unique_matches)]

        details, scores = {}, {}
        for target in TARGETS:
            channels = {}
            for family, weight in weights.items():
                best = max((m.get(target, 0.0) for m in matches[family]), default=0.0)
                winners = [m['rule_id'] for m in matches[family] if best > 0 and m.get(target, 0) == best]
                contribution = weight * best * modifier if eligibility == 'eligible' else 0.0
                channels[family] = dict(strength=best, weight=weight,
                                        contribution=contribution, winning_rules=winners,
                                        credit_per_winning_rule=(contribution / len(winners) if winners else 0.0))
            details[target] = channels
            scores[target] = math.fsum(c['contribution'] for c in channels.values())
        warnings = []
        if kind == 'publication' and record['publication_types'] is None:
            warnings.append('publication_types_missing: default modifier=1; retraction status not established')
        if kind == 'publication' and record['mesh_terms'] is None:
            warnings.append('mesh_missing: enrich from PubMed; zero contribution is not negative evidence')
        if kind == 'publication' and record['journal'] and not matches['venue']:
            warnings.append('venue_not_in_curated_lookup: zero venue bonus')
        if kind == 'datacite' and record['resource_type'] and normalize(record['resource_type']) not in self.resources:
            warnings.append('resource_type_has_no_rule: zero resource-type bonus')
        if kind == 'datacite' and scores['overall'] > 0 and not any(scores[p] for p in PCAS):
            warnings.append('generic_output_signal_only: no supported PCA assignment')
        if sum(scores[p] > 0 for p in PCAS) > 1:
            warnings.append('multiple_PCA_signals: human review needed to select the primary research objective')
        return dict(work_key=record['work_key'], selected_record=record['record_key'], kind=kind,
                    title=record['title'], source_records=record['source_records'],
                    eligibility=eligibility, excluded_publication_types=excluded,
                    publication_type_factor=modifier, publication_type_matches=modifier_matches,
                    metadata_present=available, publication_types_present=record['publication_types'] is not None,
                    available_signal_weight=sum(weights[k] for k, value in available.items() if value),
                    scores=scores, channels=details, matches=matches,
                    unmatched_mesh=unmatched_mesh, warnings=warnings)

    def score_project(self, publications: list[dict] | None,
                      datacite_outputs: list[dict] | None,
                      provenance: dict | None = None) -> dict:
        """Score caller-linked outputs. None=not supplied/retrieved; []=supplied empty.

        publications: id/pmid/doi, title, journal, mesh_terms, publication_types.
        datacite_outputs: id/doi, title, resource_type OR raw DataCite attributes.
        Optional work_id groups verified versions/duplicate representations only.
        Input identifiers and project-output links are NOT verified by this function.
        """
        for values in (publications, datacite_outputs):
            if values is not None and not isinstance(values, list):
                raise ValueError('Each stream must be a list or null.')
        payload = dict(publications=publications, datacite_outputs=datacite_outputs,
                       provenance=provenance or {})
        canonical_json(payload)  # Require JSON-compatible, finite inputs.
        records = [_record(r, 'publication') for r in publications or []]
        records += [_record(r, 'datacite') for r in datacite_outputs or []]
        unique, duplicate_report = _deduplicate(records)
        outputs = [self._score_output(r) for r in unique]
        eligible = [o for o in outputs if o['eligibility'] == 'eligible']
        counts = {s: sum(o['kind'] == s for o in eligible) for s in ('publication', 'datacite')}
        active_weight = sum(self.config['stream_weights'][s] for s in counts if counts[s])
        effective = {s: (self.config['stream_weights'][s] / active_weight
                         if counts[s] and active_weight else 0.0) for s in counts}
        evidence = {p: [] for p in TARGETS}
        totals = {p: 0.0 for p in TARGETS}
        for output in outputs:
            aggregation_weight = (effective[output['kind']] / counts[output['kind']]
                                  if output['eligibility'] == 'eligible' and counts[output['kind']] else 0.0)
            output['project_aggregation_weight'] = aggregation_weight
            output['project_contributions'] = {p: aggregation_weight * output['scores'][p] for p in TARGETS}
            for p in TARGETS:
                value = output['project_contributions'][p]
                if value > 0:
                    channels = {family: dict(detail,
                                             project_contribution=aggregation_weight * detail['contribution'])
                                for family, detail in output['channels'][p].items() if detail['contribution'] > 0}
                    evidence[p].append(dict(work_key=output['work_key'], title=output['title'],
                                            output_score=output['scores'][p],
                                            aggregation_weight=aggregation_weight,
                                            project_contribution=value, signals=channels))
        for p in TARGETS:
            totals[p] = math.fsum(e['project_contribution'] for e in evidence[p])
            if not (-1e-12 <= totals[p] <= 1 + 1e-12):
                raise ArithmeticError('Score outside [0,1]; check configuration.')
            totals[p] = min(1.0, max(0.0, totals[p]))  # Floating point guard only.
        source_states = {s: ('not_supplied' if values is None else
                            'supplied_empty' if not values else 'supplied_records')
                         for s, values in [('publication', publications), ('datacite', datacite_outputs)]}
        coverage = {}
        for stream in counts:
            group = [o for o in eligible if o['kind'] == stream]
            fields = self.config['signal_weights'][stream]
            coverage[stream] = dict(
                state=source_states[stream], eligible_unique_works=len(group),
                effective_weight=effective[stream],
                field_coverage={f: (sum(o['metadata_present'][f] for o in group) / len(group) if group else None)
                                for f in fields},
                publication_type_coverage=(sum(o['publication_types_present'] for o in group) / len(group)
                                           if group and stream == 'publication' else None),
                mean_available_signal_weight=(sum(o['available_signal_weight'] for o in group) / len(group)
                                              if group else None),
                mean_scores={p: (math.fsum(o['scores'][p] for o in group) / len(group) if group else None)
                             for p in TARGETS})
        status = 'scored' if active_weight else ('no_outputs' if not records else 'no_eligible_weighted_outputs')
        return dict(
            status=status, score_interpretable=bool(active_weight),
            overall=totals['overall'], per_pca={p: totals[p] for p in PCAS},
            evidence=evidence, outputs=outputs, coverage=coverage,
            deduplication=duplicate_report,
            counts=dict(input_records=len(records), unique_works=len(outputs), eligible_unique_works=len(eligible)),
            scope=dict(pcas=list(PCAS), pca_definition_year=self.config['pca_definition_year'],
                       interpretation='observed output signal index; not probability, budget share, or official classification',
                       project_output_linkage='caller_supplied_not_verified_by_scorer'),
            warnings=[
                'Exploratory weights and mappings; no empirical validity claim.',
                'Source retrieval completeness and attribution must be established upstream.',
                'Per-PCA scores overlap; do not sum them or treat them as budget allocations.',
                'Compare projects only with compatible output windows and metadata/source coverage.'
            ],
            reproducibility=dict(scorer_version=VERSION, rule_version=self.config['rule_version'],
                                 input_sha256=digest(payload), config_sha256=digest(self.config),
                                 code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                                 canonicalization='UTF-8 JSON; sorted keys; compact separators; finite values only',
                                 source_provenance=copy.deepcopy(provenance or {})))


def score_project(publications: list[dict] | None,
                  datacite_outputs: list[dict] | None,
                  config: dict | None = None,
                  provenance: dict | None = None) -> dict:
    return Scorer(config).score_project(publications, datacite_outputs, provenance)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path, help='JSON object with publications/datacite_outputs')
    parser.add_argument('--rules', type=Path, default=Path(__file__).with_name('rules.json'))
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    data = json.loads(args.input.read_text(encoding='utf-8'))
    result = Scorer(load_config(args.rules)).score_project(
        data.get('publications'), data.get('datacite_outputs'), data.get('provenance'))
    rendered = json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + '\n'
    if args.output:
        args.output.write_text(rendered, encoding='utf-8')
    else:
        print(rendered, end='')


if __name__ == '__main__':
    main()
