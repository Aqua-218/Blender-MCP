# Evaluation Matrix: Metadata Store

## Candidates

- SQLite
- PostgreSQL
- Flat JSON files

## Weighted Criteria

| Criterion | Weight |
| --- | ---: |
| Local application fit | 30 |
| Queryability | 20 |
| Operational simplicity | 20 |
| Concurrency headroom | 15 |
| Migration path | 15 |

## Scores

| Candidate | Local Fit | Queryability | Ops Simplicity | Concurrency | Migration Path | Weighted Total |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| SQLite | 10 | 8 | 10 | 6 | 8 | 8.65 |
| PostgreSQL | 5 | 10 | 4 | 10 | 10 | 7.30 |
| JSON files | 7 | 3 | 8 | 4 | 4 | 5.25 |

## Recommendation

Select SQLite with WAL mode for the first implementation.

## Evidence

- SQLite is explicitly recommended for application-local storage, file-format style persistence, and single-application server use cases.
- SQLite is not the right fit for many concurrent writers across many machines; that is acceptable for the first deployment model.

## Rejected Options

- PostgreSQL is the likely migration target for hosted multi-worker deployments, but not necessary for the local-first product.
- Flat files are too weak for history, QA, diff, and indexing workflows.