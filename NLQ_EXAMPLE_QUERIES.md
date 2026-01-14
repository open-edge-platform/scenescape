# Example NLQ Queries for Testing

## Tripwire Crossing Queries (people entering/exiting)

1. "How many people crossed the checkout in the last 30 minutes?"
2. "Show me all checkout crossings in the last hour"
3. "How many people entered through the checkout today?"
4. "Count people who crossed the checkout going forward in last 5 minutes"
5. "Show backward crossings at the checkout in the last hour"

## Region Count Queries (people in regions)

6. "How many people are in the waiting area right now?"
7. "Show person count in the waiting area over the last hour"
8. "How many people were in the checkout area in the last 30 minutes?"
9. "Count people in all regions in the last hour"
10. "Show me the waiting area person count today"

## Dwell Time Queries (time spent in regions)

11. "What is the average dwell time in the waiting area?"
12. "How long do people spend in the checkout area?"
13. "Show dwell time for all people in the last hour"
14. "What's the average time spent in the waiting area today?"
15. "Show me dwell times for the checkout area in the last 30 minutes"

## General Analytics Queries

16. "Show all analytics data from the last hour"
17. "Show recent events from the last 5 minutes"
18. "What activity happened in the last 30 minutes?"
19. "Show all person tracking data from today"
20. "Give me a summary of all events in the last 2 hours"

## Testing Tips

- **Good keywords for tripwires**: "crossed", "entered", "exited", "went through", "crossing"
- **Good keywords for regions**: "in the", "how many in", "count in"
- **Good keywords for dwell**: "time spent", "how long", "dwell time", "average time"
- **Time ranges**: "last 5 minutes", "last 30 minutes", "last hour", "today" (24 hours)

## Expected Measurements

- **tripwire_crossings**: For entrance/exit counting
- **region_obj_count_2**: For "how many people in X area"
- **region_obj_dwell_2**: For "how long did people spend"
- **person_loc**: For location coordinates (rarely needed)
