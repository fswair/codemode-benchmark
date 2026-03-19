## Flash — Eski (1 tur) vs Yeni (2 tur)

| Metrik | Eski (single-shot) | Yeni (feedback-guided) | Fark |
|---|---|---|---|
| **Pass Rate** | **2/3** (flatten FAIL) | **3/3** | +1 senaryo kurtarıldı |
| **Avg Coverage** | 98.3% | **100%** | +1.7pp |
| **Total Refinements** | 4 (flatten 3, parse_cron 1) | **0** | Sıfıra indi |
| **Avg Cases** | 25.7 | **45.3** | **+76%** |
| **Avg Raises** | 8.3 | **11.3** | +36% |
| **Avg Snippets** | 23.0 | **40.0** | +74% |
| **Avg Time** | 38.8s | 57.0s | +18.2s (2. tur maliyeti) |

### Per-scenario karşılaştırma

| Senaryo | Eski | Yeni |
|---|---|---|
| **flatten** | **FAIL** (95%, 3 refine, 27 case) | **PASS** (100%, 0 refine, 49 case) |
| **parse_cron** | PASS (100%, 1 refine, 27 case) | PASS (100%, **0 refine**, **45 case**) |
| **levenshtein** | PASS (100%, 0 refine, 23 case) | PASS (100%, 0 refine, **42 case**) |

### Öne çıkan noktalar

1. **flatten artık geçiyor.** Eski pipeline'da Flash flatten'ı 3 refinement'tan sonra bile geçemiyordu (95%'de kalıyordu). Yeni pipeline'da **sıfır refinement ile 100%**.

2. **Refinement tamamen ortadan kalktı.** 3 senaryoda toplam 0 refinement. Eski pipeline'da 4 refinement vardı. Bu, Round 2'nin spec generation'a giden evidence kalitesini dramatik artırdığını gösteriyor.

3. **Case sayısı neredeyse 2 katına çıktı.** 25.7 → 45.3. Round 2'den gelen ek snippet'lar spec ajanına daha zengin veri sağlıyor, ajan da daha fazla ve daha çeşitli test case üretiyor.

4. **Süre artışı makul.** +18.2s (2. tur LLM call + execution). Ama eski pipeline'daki 4 refinement round'u da zaman harcıyordu — toplam pipeline süresi göz önüne alındığında net maliyet düşük.

5. **Flash artık Opus'un eski skorlarına yaklaştı.** Opus single-shot'ta 42.3 avg case üretiyordu; Flash 2 turla 45.3'e ulaştı. Feedback-guided exploration, zayıf modelin kalite açığını kapattı.

ChatGPT haklıymış: **pipeline'daki en yüksek ROI'lı değişiklik buydu.**