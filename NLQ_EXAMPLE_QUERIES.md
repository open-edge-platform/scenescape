# Example NLQ Queries for Testing

## Tripwire Crossing Queries (people entering/exiting)

1. "How many people entered in the last 30 minutes?"
2. "Show me all entry crossings in the last hour"
3. "How many people entered through the entry today?"
4. "Count people who entered in the last 5 minutes"
5. "Show people who exited in the last hour"
6. "How many people crossed the entry going forward?"

## Region Count Queries (people in regions)

7. "How many people are in the demo room right now?"
8. "Show person count in the waiting area over the last hour"
9. "How many people are in the tray area in the last 30 minutes?"
10. "Count people in all regions in the last hour"
11. "Show me the demo room person count today"
12. "How many people are at the tray right now?"

## Dwell Time Queries (time spent in regions)

13. "What is the average dwell time in the waiting area?"
14. "How long do people spend in the tray area?"
15. "Show dwell time for all people in the last hour"
16. "What's the average time spent in the demo room today?"
17. "Show me dwell times for the tray area in the last 30 minutes"

## General Analytics Queries

18. "Show all analytics data from the last hour"
19. "Show recent events from the last 5 minutes"
20. "What activity happened in the last 30 minutes?"

## Testing Tips

- **Good keywords for tripwires**: "entered", "exited", "went through", "came in", "left", "crossed"
- **Good keywords for regions**: "in the", "how many in", "count in", "people in", "currently in"
- **Good keywords for dwell**: "time spent", "how long", "dwell time", "average time", "duration"
- **Time ranges**: "last 5 minutes", "last 30 minutes", "last hour", "today" (24 hours)

## Available Regions and Tripwires

- **Regions**: 
  - "demo_room" (also matches: waiting area, waiting room, demo room)
  - "tray_area" (also matches: tray, serving area, tray area)
- **Tripwires**: 
  - "entry" (the entry/entrance point)

## Expected Measurements

- **tripwire_crossings**: For entrance/exit counting (use tripwire="entry", direction="forward" or "backward")
- **region_obj_count_2**: For "how many people in X area" (occupancy snapshots)
- **region_obj_dwell_2**: For "how long did people spend" (dwell time in seconds)
- **person_loc**: For location coordinates (rarely needed for most queries)
