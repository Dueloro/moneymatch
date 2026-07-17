> **Status: incorporated with one structural rejection (2026-07-15).** Migrated
> from the PoC repo. The player-performance-profile, challenge-immutability,
> audit, grading, fraud-signal, and risk-monitoring designs here are adopted
> into the [implementation guide](../implementation-guide/00-README.md)
> (Phases 2, 3, 4, 6). **The "House-Backed Performance Challenges" mode (§1
> mode 1, §10 payout formula) is rejected**: a platform-funded fixed payout
> puts the house on the other side of the wager, which contradicts the
> neutral-operator legal frame — see
> [`../product/overview.md`](../product/overview.md) §10.4 and
> [`../legal/legal-compliance.md`](../legal/legal-compliance.md) §1.3. The
> same personalized-threshold engine ships instead as **pooled** solo rooms
> (guide Phase 4): entrant-funded prizes, rake-only, percentile-derived
> personal bars.

# Challenge engine workflow  
  
## Money Match Challenge Engine Workflow  
## 1. Core Objective  
Build a challenge engine that generates personalized, data-driven, auditable gaming challenges based on a player’s historical performance.  
The engine should support two modes:  
1. **House-Backed Performance Challenges**    
    * Money Match offers the user a challenge.  
    * The user pays an entry fee.  
    * The user receives a fixed payout if the challenge is completed.  
2. **Peer-to-Peer Asynchronous Skill Contests**    
    * Two users compete on the same or comparable performance metric.  
    * Both pay an entry fee.  
    * Winner receives prize pool minus platform fee.  
The system must prioritize:  
* Trust  
* Transparency  
* Auditability  
* Anti-fraud  
* Profitability  
* Legal review readiness  
   
⸻  
   
## 2. High-Level System Flow  
## User Flow  
1. User creates Money Match account.  
2. User links game account, starting with FACEIT.  
3. System imports recent match history.  
4. System builds player performance profile.  
5. System generates available challenges.  
6. User selects challenge.  
7. Challenge terms are locked before entry.  
8. User pays entry fee.  
9. User plays eligible match or match set.  
10. System retrieves verified match data.  
11. System grades challenge.  
12. Result is stored in audit log.  
13. User receives payout, refund, or loss outcome.  
   
⸻  
   
## 3. Data Collection Layer  
## Purpose  
Collect clean, reliable match data from supported game APIs.  
## Initial API Source  
* FACEIT API  
## Future API Sources  
* Clash Royale API  
* Riot API  
* Steam / CS2 data if needed  
* Tracker-style third-party APIs only if allowed  
## Data to Store  
For each player:  
* Money Match user ID  
* Game account ID  
* FACEIT player ID  
* Game title  
* Region  
* Rank / Elo  
* Match history  
* Match timestamps  
* Match IDs  
* Map / mode  
* Team result  
* Individual stats  
* Match duration  
* Opponent/team context if available  
## CS2 Example Stats  
* Kills  
* Deaths  
* Assists  
* K/D ratio  
* ADR  
* Headshot percentage  
* MVPs  
* Utility damage  
* Flash assists  
* Match result  
* Map  
* FACEIT Elo  
* Match level  
## Data Requirements  
The engine should require a minimum amount of historical data before real-money challenges are offered.  
Recommended minimum:  
* At least 25 recent matches for limited challenges  
* At least 50 recent matches for full challenge eligibility  
* At least 100 matches for higher-stakes challenges  
If a user has insufficient history, they can access:  
* Free challenges  
* Low-stakes starter challenges  
* P2P only  
* Delayed eligibility until more data is collected  
   
⸻  
   
## 4. Match Ingestion Workflow  
## Step 1: Account Link  
User connects FACEIT account.  
System stores:  
* FACEIT player ID  
* Username  
* Region  
* Game IDs  
* Initial Elo/rank  
* Account creation date if available  
## Step 2: Historical Pull  
System pulls last 50–100 matches.  
For each match:  
* Save raw API response.  
* Parse normalized stats.  
* Store both raw and processed data.  
Important: Always preserve the raw API response for audit purposes.  
## Step 3: Ongoing Sync  
System checks for new matches:  
* On user login  
* When user accepts challenge  
* After estimated match completion  
* Periodically in background  
## Step 4: Match Eligibility Filter  
Not every match should qualify.  
Reject matches if:  
* Match was already started before challenge acceptance.  
* Match is outside challenge window.  
* Match type is unsupported.  
* Stats are incomplete.  
* API data is inconsistent.  
* Match appears manipulated.  
* Match is not from the linked account.  
   
⸻  
   
## 5. Player Performance Profile  
## Purpose  
Create a statistical profile of each user’s normal performance.  
For each metric, calculate:  
* Mean  
* Median  
* Standard deviation  
* Minimum  
* Maximum  
* 25th percentile  
* 50th percentile  
* 60th percentile  
* 70th percentile  
* 75th percentile  
* 80th percentile  
* 85th percentile  
* 90th percentile  
* 95th percentile  
* Recent trend  
* Volatility score  
* Confidence score  
## Rolling Windows  
Use multiple rolling windows:  
* Last 10 matches  
* Last 25 matches  
* Last 50 matches  
* Last 100 matches if available  
Why:  
* Last 10 captures current form.  
* Last 50 captures true ability.  
* Last 100 captures long-term stability.  
## Performance Profile Example  
{  
  "user_id": "mm_123",  
  "game": "cs2",  
  "metric": "kills",  
  "sample_size": 50,  
  "mean": 17.4,  
  "median": 17,  
  "std_dev": 5.2,  
  "p60": 19,  
  "p75": 22,  
  "p85": 25,  
  "p90": 28,  
  "recent_10_avg": 18.1,  
  "confidence_score": 0.86,  
  "volatility_score": 0.31  
}  
   
⸻  
   
## 6. Confidence Score  
## Purpose  
The confidence score tells the system how trustworthy the player profile is.  
Higher confidence means:  
* More challenge options  
* Higher max entry limits  
* More accurate pricing  
Lower confidence means:  
* Lower entry limits  
* Fewer challenges  
* More conservative payouts  
## Inputs  
Confidence score should consider:  
* Number of matches  
* Consistency of performance  
* Recency of data  
* API reliability  
* Account age  
* Rank stability  
* Fraud flags  
## Example Tiers  
**Low Confidence**  
* Less than 25 matches  
* New account  
* High volatility  
* Recent rank jump  
* Fraud flags  
Allowed:  
* Free challenges  
* Low-stakes challenges only  
**Medium Confidence**  
* 25–50 matches  
* Stable account  
* Moderate volatility  
Allowed:  
* Standard challenges  
**High Confidence**  
* 50+ matches  
* Stable rank  
* Low fraud signals  
* Consistent API history  
Allowed:  
* Full challenge menu  
* Higher entry caps  
   
⸻  
   
## 7. Challenge Generation  
## Core Principle  
Challenges should be generated from historical performance, not arbitrary odds.  
The challenge must be explainable.  
Bad:  
“Our AI thinks this is fair.”  
Good:  
“This challenge is based on your 75th percentile performance over your last 50 FACEIT matches.”  
## Challenge Difficulty Tiers  
Recommended v1 tiers:  
**Easy**  
* Target around player’s 60th percentile  
* Expected completion: approximately 40–45%  
**Medium**  
* Target around player’s 75th percentile  
* Expected completion: approximately 25–35%  
**Hard**  
* Target around player’s 85th–90th percentile  
* Expected completion: approximately 10–20%  
Do not call these odds publicly unless counsel approves. Internally, track expected completion probability.  
## Example CS2 Challenges  
* Get at least 20 kills in your next FACEIT match.  
* Get at least 85 ADR in your next FACEIT match.  
* Get at least 3 assists in your next FACEIT match.  
* Get at least [1.15 K](x-apple-data-detectors://embedded-result/5839)/D in your next FACEIT match.  
* Win your match and get at least 15 kills.  
Prefer individual performance metrics over team outcome metrics.  
## Safer Initial Metrics  
Start with metrics most directly tied to individual skill:  
* Kills  
* ADR  
* ACS  
* Crowns  
* Damage  
* Assists  
* K/D  
* Headshot percentage only if sample is stable  
Avoid early reliance on:  
* Team wins  
* Teammate-dependent stats  
* Opponent-dependent stats  
* Highly random or noisy stats  
   
⸻  
   
## 8. Challenge Object Schema  
Every challenge should be stored as an immutable object once accepted.  
{  
  "challenge_id": "ch_001",  
  "user_id": "mm_123",  
  "game": "cs2",  
  "mode": "house_backed",  
  "metric": "kills",  
  "target": 22,  
  "comparison": ">=",  
  "entry_fee": 5.00,  
  "potential_payout": 8.50,  
  "difficulty": "medium",  
  "basis": {  
    "sample_size": 50,  
    "percentile_used": 75,  
    "historical_mean": 17.4,  
    "historical_median": 17,  
    "historical_p75": 22  
  },  
  "eligible_match_type": "FACEIT_5v5_ranked",  
  "accepted_at": "timestamp",  
  "expires_at": "timestamp",  
  "status": "accepted",  
  "locked": true  
}  
Once accepted:  
* Entry fee cannot change.  
* Target cannot change.  
* Payout cannot change.  
* Eligible match rules cannot change.  
   
⸻  
   
## 9. Challenge Locking Rules  
Before payment, user must see:  
* Game  
* Metric  
* Target  
* Entry fee  
* Potential payout  
* Match eligibility rules  
* Expiration window  
* What happens if API fails  
* What happens if no eligible match is played  
After acceptance:  
* Challenge is locked.  
* System records timestamp.  
* System records current player profile snapshot.  
* System records exact algorithm version used.  
* System records challenge-generation inputs.  
This is critical for trust and future legal review.  
   
⸻  
   
## 10. Payout Framework  
## House-Backed Challenge Payouts  
The system should calculate payouts based on:  
* Entry fee  
* Difficulty tier  
* Expected completion rate  
* Platform margin  
* Player confidence score  
* Fraud risk  
* Bankroll exposure limits  
## Example Internal Formula  
Expected payout should be lower than expected entry revenue over time.  
Simplified:  
expected_cost = probability_of_success * payout  
expected_revenue = entry_fee  
platform_margin = expected_revenue - expected_cost  
Example:  
* Entry fee: $5  
* Estimated success probability: 30%  
* Payout: $12  
* Expected cost: $3.60  
* Expected margin: $1.40  
Do not expose all internal pricing details publicly.  
Expose enough for trust:  
* Challenge basis  
* Difficulty  
* Target  
* Payout  
## Payout Guardrails  
* Cap max payout for new users.  
* Cap max entry for low-confidence users.  
* Cap daily exposure per user.  
* Cap exposure per game.  
* Cap exposure per metric.  
* Pause challenge type if completion rate exceeds expected range.  
* Require manual review for abnormal winning streaks.  
   
⸻  
   
## 11. Risk Management Engine  
## Purpose  
Protect the bankroll from bad challenge pricing, fraud, and exploitation.  
## Track  
For every challenge type:  
* Number offered  
* Number accepted  
* Completion rate  
* Expected completion rate  
* Gross entry fees  
* Gross payouts  
* Net margin  
* User repeat rate  
* Dispute rate  
* Fraud rate  
## Risk Alerts  
Trigger alerts if:  
* Completion rate exceeds expected rate by large margin.  
* A user wins too many high-difficulty challenges.  
* A metric is consistently mispriced.  
* A game mode has abnormal results.  
* A new exploit pattern appears.  
* API data quality drops.  
## Critical Rule  
Risk engine may adjust future challenge generation.  
Risk engine may not alter active accepted challenges.  
   
⸻  
   
## 12. Peer-to-Peer Challenge Workflow  
## User Flow  
1. User selects P2P contest.  
2. System selects metric and challenge window.  
3. User enters with entry fee.  
4. System matches user with similar player.  
5. Both users complete eligible matches.  
6. System grades both results.  
7. Winner receives prize pool minus fee.  
## Matching Criteria  
Match players based on:  
* Game  
* Region  
* Rank/Elo  
* Confidence score  
* Selected metric  
* Recent performance  
* Entry amount  
* Challenge window  
## P2P Contest Object  
{  
  "contest_id": "p2p_001",  
  "game": "cs2",  
  "metric": "kills",  
  "entry_fee": 5.00,  
  "platform_fee": 1.00,  
  "prize_pool": 9.00,  
  "players": ["mm_123", "mm_456"],  
  "matching_basis": {  
    "elo_difference": 87,  
    "metric_percentile_similarity": "medium",  
    "confidence_scores": [0.86, 0.82]  
  },  
  "eligible_window": {  
    "starts_at": "timestamp",  
    "ends_at": "timestamp"  
  },  
  "status": "active"  
}  
## P2P Rules  
* Both players must know the scoring metric before entry.  
* Entry fees are fixed.  
* Prize pool is fixed.  
* Platform fee is disclosed.  
* Rules cannot change after entry.  
* If one player fails to complete required match, apply predefined forfeit/refund rule.  
* If API fails, apply predefined void/refund rule.  
   
⸻  
   
## 13. Grading Engine  
## Purpose  
Automatically determine whether a challenge was won, lost, voided, or flagged.  
## Grading Steps  
1. Identify eligible match.  
2. Pull final stats from API.  
3. Validate match timestamp.  
4. Validate match type.  
5. Validate linked account.  
6. Validate metric.  
7. Compare result to target.  
8. Assign outcome.  
9. Save grading proof.  
10. Update user wallet.  
## Outcomes  
Possible statuses:  
* Won  
* Lost  
* Voided  
* Refunded  
* Expired  
* Flagged for review  
* Pending API data  
## Example  
Challenge:  
* Metric: kills  
* Target: 22  
* User result: 24  
Outcome:  
* Won  
Store:  
{  
  "challenge_id": "ch_001",  
  "match_id": "faceit_match_999",  
  "metric": "kills",  
  "target": 22,  
  "actual": 24,  
  "outcome": "won",  
  "graded_at": "timestamp",  
  "api_response_id": "raw_abc123"  
}  
   
⸻  
   
## 14. Audit Log  
Every important event must be logged.  
## Log Events  
* Account linked  
* Historical data imported  
* Player profile generated  
* Challenge generated  
* Challenge viewed  
* Challenge accepted  
* Entry fee paid  
* Challenge locked  
* Match detected  
* Match graded  
* Payout issued  
* Challenge voided  
* User dispute opened  
* Admin review performed  
* Fraud flag triggered  
## Audit Log Requirements  
Each log should include:  
* Timestamp  
* User ID  
* Event type  
* Object ID  
* Raw data reference  
* Algorithm version  
* Admin ID if applicable  
* Before/after values if changed  
This protects the company during disputes and legal review.  
   
⸻  
   
## 15. Fraud Detection  
## Key Threats  
* Smurfing  
* Boosting  
* Account sharing  
* VPN usage  
* Multi-accounting  
* Botting  
* Match throwing  
* Queue manipulation  
* Playing with collusive teammates  
* Deliberately lowering stats before accepting challenges  
## Fraud Signals  
Track:  
* New account with elite stats  
* Sudden performance jump  
* Sudden performance drop before challenges  
* Multiple Money Match accounts using same game account  
* Multiple users sharing device/payment method  
* VPN or proxy use  
* Repeated challenge wins after weak historical performance  
* Unusual match timing  
* Abnormal opponent patterns  
* Abnormal teammate patterns  
* High dispute frequency  
## Fraud Response  
Possible actions:  
* Lower confidence score  
* Limit max entry  
* Restrict challenge types  
* Require additional verification  
* Delay withdrawal  
* Flag for manual review  
* Suspend account  
* Ban account  
All fraud actions should be documented.  
   
⸻  
   
## 16. API Failure Handling  
Predefine rules before launch.  
## If API is delayed  
* Challenge remains pending.  
* User is informed.  
* System retries periodically.  
## If API is unavailable  
Options:  
* Void and refund.  
* Wait until API returns.  
* Manual review if reliable proof exists.  
## If data is incomplete  
* Void and refund unless rules clearly allow grading.  
## If match cannot be verified  
* Void or loss depending on disclosed rule.  
* For trust, early version should favor refund/void.  
Recommended v1 policy:  
If Money Match cannot verify the outcome through approved data sources, the challenge is voided and entry fee refunded.  
   
⸻  
   
## 17. User Transparency Layer  
The UI should explain each challenge clearly.  
## Challenge Card Should Show  
* Game  
* Challenge target  
* Entry fee  
* Potential payout  
* Difficulty  
* Eligible match type  
* Expiration  
* Data basis  
Example:  
CS2 Challenge  
  
Get 22+ kills in your next FACEIT 5v5 match.  
  
Entry: $5  
Payout if completed: $8.50  
Difficulty: Medium  
  
Based on your last 50 FACEIT matches:  
Average kills: 17.4  
75th percentile: 22  
This builds trust and differentiates Money Match from competitors.  
   
⸻  
   
## 18. Admin Dashboard  
Build internal tools from the beginning.  
## Admin Views  
* User profile  
* Linked accounts  
* Match history  
* Challenge history  
* Wallet history  
* Fraud flags  
* Disputes  
* API logs  
* Risk dashboard  
* Revenue dashboard  
## Admin Actions  
* View audit trail  
* Void challenge  
* Refund user  
* Freeze withdrawal  
* Add fraud note  
* Ban user  
* Adjust user limits  
Important: Admins should not be able to change accepted challenge terms.  
   
⸻  
   
## 19. Versioning  
Every algorithm update must be versioned.  
Store:  
* Challenge engine version  
* Risk model version  
* Grading engine version  
* Fraud model version  
Why:  
If a user disputes a challenge, Money Match needs to know exactly which rules generated and graded it.  
Example:  
{  
  "challenge_engine_version": "v0.3.2",  
  "grading_engine_version": "v0.2.8",  
  "risk_engine_version": "v0.1.4"  
}  
   
⸻  
   
## 20. Testing Plan  
## Unit Tests  
Test:  
* Percentile calculations  
* Challenge generation  
* Challenge locking  
* Match eligibility  
* Grading logic  
* Payout calculations  
* Refund logic  
## Simulation Tests  
Run historical simulations.  
Example:  
Use 10,000 historical matches.  
Ask:  
* What challenges would we have offered?  
* How often would users have won?  
* Would Money Match have made money?  
* Which metrics are mispriced?  
* Which players exploit the system?  
## Shadow Mode  
Before real-money launch:  
* Generate challenges silently.  
* Do not show users.  
* Compare predicted success to actual results.  
Then:  
* Show free challenges.  
* Track completion rates.  
* Refine engine.  
## Real-Money Readiness Criteria  
Do not launch real-money challenges until:  
* API integration is stable.  
* Grading is reliable.  
* Completion rates are understood.  
* Fraud controls exist.  
* Legal review is complete.  
* Payment processing is approved.  
* Terms and rules are finalized.  
* Refund/void rules are implemented.  
   
⸻  
   
## 21. Recommended MVP Build Order  
## MVP 1: Free Challenge Engine  
Build:  
* User login  
* FACEIT account link  
* Match history import  
* Player profile  
* Challenge generation  
* Challenge cards  
* Match grading  
* Challenge history  
No deposits.  
No payouts.  
Goal: Prove the engine works.  
## MVP 2: Internal Risk Simulation  
Build:  
* Historical backtesting  
* Expected margin calculation  
* Completion rate tracking  
* Metric-level profitability dashboard  
Goal: Know whether the business model works.  
## MVP 3: P2P Without Cash  
Build:  
* Matchmaking  
* P2P contests  
* Leaderboards  
* XP rewards  
Goal: Test whether users like competing asynchronously.  
## MVP 4: Sponsored / Promotional Prizes  
Build:  
* Free entry  
* Prize leaderboard  
* Manual prize fulfillment if necessary  
Goal: Test real reward behavior without deposit-based risk.  
## MVP 5: Real-Money Pilot  
Only after legal review.  
Build:  
* Wallet  
* Deposits  
* Withdrawals  
* KYC  
* Geofencing  
* Responsible play controls  
* Real-money challenge rules  
* Tax reporting process if needed  
   
⸻  
   
## 22. Development Priorities  
Highest priority:  
1. Data accuracy  
2. Challenge immutability  
3. Audit logs  
4. Grading reliability  
5. Fraud detection  
6. Backtesting  
7. User transparency  
8. Risk controls  
Lower priority at first:  
* Beautiful animations  
* Social feed  
* Complex betting-style UI  
* Too many games  
* Too many metrics  
* Large payouts  
   
⸻  
   
## 23. Initial Launch Recommendation  
Start with:  
## Game  
CS2 through FACEIT.  
## Metrics  
* Kills  
* ADR  
* Assists  
* K/D  
## Modes  
* Free house-backed style challenges  
* Free P2P contests  
## Challenge Tiers  
* Easy  
* Medium  
* Hard  
## Data Window  
* Last 50 FACEIT matches  
## Required History  
* Minimum 25 matches  
* Full eligibility at 50 matches  
## User Trust Feature  
Every challenge should show:  
* Average  
* Percentile basis  
* Difficulty  
* Exact grading rule  
   
⸻  
   
## 24. Final Challenge Engine Philosophy  
The challenge engine should not feel like a black box.  
It should feel like:  
“Money Match understands how good I am and gives me fair, exciting challenges that I can verify.”  
That is the product moat.  
The companies that lose trust in this space will feel like casinos.  
Money Match should feel like competitive gaming with transparent stakes.  
