# Οδηγός Δεικτών

Αυτός ο οδηγός αφαιρέθηκε από το εβδομαδιαίο email (το έκανε πολύ μεγάλο —
το Gmail κόβει μηνύματα >~102KB, "[Message clipped]"). Μένει εδώ, μόνιμα
διαθέσιμο, χωρίς να χρειάζεται να το ψάχνεις σε κάθε email.

| Δείκτης | Πηγή | Τι μετράει & γιατί χρησιμοποιείται | Threshold |
|---|---|---|---|
| **P/E Ratio** | Benjamin Graham | Τιμή μετοχής ÷ κέρδη ανά μετοχή (EPS). Δείχνει πόσα € πληρώνεις για κάθε € κέρδους. Χαμηλό P/E = η αγορά δεν περιμένει μεγάλη ανάπτυξη — ευκαιρία για value investor. Αδυναμία: αγνοεί χρέος και ποιότητα κερδών. | <15 ιδανικό, <20 αποδεκτό |
| **P/B Ratio** | Benjamin Graham | Τιμή προς Λογιστική Αξία (assets - liabilities). Αν P/B<1, η μετοχή κοστίζει λιγότερο από τα καθαρά assets — σπάνιο, ισχυρό signal. Χρήσιμο για banks/industrials, λιγότερο για tech (άυλα assets). | <1.5 ιδανικό, <2.5 αποδεκτό |
| **DCF MoS** (Base/Bear/Bull) | Graham + Buffett | Discounted Cash Flow — εσωτερική αξία βάσει μελλοντικών ταμειακών ροών (5ετής ορίζοντας + terminal value). Margin of Safety = πόσο % κάτω από αυτή την αξία είναι η τρέχουσα τιμή. Bear case: fat tail assumptions (Taleb) — growth -3%, WACC +2%. | MoS>20% buying zone, >30% ισχυρό. **Προσοχή**: MoS>300% φιλτράρεται αυτόματα ως πιθανό computation artifact (δες FIX Q) |
| **Graham Formula** | Benjamin Graham | EPS × (8.5 + 2×growth%) × (4.4/bond yield). Γρήγορη, διαχρονική δεύτερη γνώμη δίπλα στο DCF. Τείνει να υπερτιμά growth stocks, αγνοεί χρέος. | MoS>30% ισχυρό — χρήση ως confirmation |
| **EV/EBITDA** | Hedge Funds (Citadel/D.E. Shaw) | Enterprise Value (market cap + χρέος - cash) ÷ EBITDA. Καλύτερο από P/E για εταιρείες με χρέος/διαφορετική κεφαλαιακή δομή. Δημοφιλές σε M&A αποτιμήσεις. | <8x φθηνό, 8-12x μέτριο, >12x ακριβό |
| **ROE Quality** | Warren Buffett | Return on Equity. Ο Buffett απαιτεί ROE>15% για ποιοτική εταιρεία. Αδυναμία: υψηλό leverage εμφανίζει τεχνητά υψηλό ROE. | ≥15% ισχυρό, 10-15% αποδεκτό, <10% ανησυχητικό |
| **ROIC est. (proxy)** | Graham + Buffett | ROE × (1/(1+D/E)) — αφαιρεί leverage effect. **Proxy, όχι ακριβής NOPAT/Invested Capital υπολογισμός.** Consumer staples με υγιές χρέος υποεκτιμώνται. | Proxy>WACC = πιθανή αξία — ένδειξη μόνο |
| **52-Week Low Proximity** | Behavioral Finance (Kahneman/Thaler) | Πόσο % πάνω από 52w low. Contrarian signal — investors υπεραντιδρούν σε bad news. | <15% από low = strong signal, 15-30% neutral, >30% απομακρύνθηκε |
| **Fragility Score** | Nassim Taleb | Ευαισθησία σε Black Swans, βάσει D/E και Beta. Informational flag, όχι φίλτρο. | 🛡 Antifragile: D/E<1 + Beta<1 · ⚖ Neutral: μέτρια · ⚠ Fragile: D/E>2 + Beta>1.3 |
| **Risk Overall** (4 διαστάσεις) | Multi-framework | Επιχειρηματικός (D/E, Beta) + Αποτίμησης (P/E, P/B) + Μακροοικονομικός (κύκλος) + Sector risk. | Χαμηλός + MoS>20% = ideal combo |
| **Beta** | CAPM / Graham | Μεταβλητότητα σχετικά με την αγορά. 1.0=S&P500, <1 πιο σταθερή, >1 πιο ευμετάβλητη. Χρησιμοποιείται στο WACC. | <1.0 Graham-friendly |
| **WACC** | Corporate Finance | Risk-Free Rate (4.2%) + Beta × Equity Risk Premium (5.5%) — discount rate του DCF. | Τυπικά 7-12%· χαμηλό Beta = χαμηλό WACC = υψηλότερη αξία |
| **Analyst Target & Upside** | Consensus | Μέσος στόχος τιμής sell-side analysts. Προσοχή: συστηματική ανοδική προκατάληψη. Ισχυρότερο όταν συγκλίνει με DCF base. | >15% upside ενισχύει thesis — confirmation μόνο |
| **Dividend Yield** | Graham / Income | Ετήσιο μέρισμα ÷ τρέχουσα τιμή. Παρέχει "floor" αξίας. | 2-4% υγιές, >4% υψηλό, >8% suspicious |
| **Sector Valuation (P/E vs Ιστορικό)** | — | Συγκρίνει το τρέχον P/E ενός κλάδου με το ιστορικό μέσο όρο ΤΟΥ ΙΔΙΟΥ κλάδου (όχι με άλλους κλάδους). Ένας "φθηνός" κλάδος δεν σημαίνει φτηνή μετοχή μέσα σε αυτόν. | 🟢 Φθηνός ≤ threshold · 🟡 Fair Value κοντά στο μέσο · 🔴 Ακριβός ≥ threshold |
| **Tier (STRONG BUY/BUY/HOLD/AVOID)** | Πολυπαραγοντικό σύστημα | Συνδυάζει: valuation convergence (DCF+Graham+EV/EBITDA+analyst) + quality (ROE/ROIC/D-E) + macro alignment + EPS-quality gate + data-completeness gate. Δες `tier_reason` σε κάθε μετοχή για ακριβή εξήγηση. | STRONG BUY: score≥65 + data≥75% · BUY: score≥45 + data≥60% · HOLD: score≥25 ή data<50% · AVOID: τα άλλα |

**Δεν αποτελεί επενδυτική συμβουλή.** Φίλτρα screener: P/E<20 · P/B<2.5 · DCF Base MoS>15%.
