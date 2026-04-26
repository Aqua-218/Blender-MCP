# Load Testing

## Objectives

- Measure queue behavior under multiple heavy requests
- Validate timeout behavior
- Confirm resource ceilings are enforced

## Test Cases

- Burst of 20 lightweight inspection calls
- Queue of 5 final renders
- Oversized scatter request that should be rejected by policy
- Repeated snapshot-heavy revision loop over 20 iterations

## Metrics

- Queue wait time
- Tool completion rate
- Controller memory growth trend
- Timeout count