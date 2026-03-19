## Opus 4.6 vs Flash — Detaylı Analiz

### 1. Headline Numbers

| Metrik | Opus 4.6 | Flash | Fark |
|---|---|---|---|
| Pass Rate | **3/3** | 2/3 | Opus kazanır |
| Avg Coverage | **100%** | 98.3% | +1.7pp |
| Total Refinements | **0** | 4 | Opus: zero-shot perfection |
| Avg Cases | **42.3** | 25.7 | +65% |
| Avg Raises Cases | **11.7** | 8.3 | +41% |
| Avg Time | 102.8s | **38.8s** | Flash 2.65x hızlı |

En çarpıcı bulgu: **Opus 3 senaryoyu da sıfır refinement ile 100% coverage'a ulaştı.** Flash, flatten'da 3 refinement harcadı ve hâlâ 95%'de kaldı (FAIL).

---

### 2. Per-Scenario Deep Dive

#### flatten (Flash'in en zayıf senaryosu)

**Opus**: 30 case, 7 raises, 0 refine, 100% — ilk seferde temiz geçti.
**Flash**: 27 case, 9 raises, 3 refine, 95% — **FAIL**.

Kalite farkları:

| Boyut | Opus | Flash |
|---|---|---|
| Global evaluators | 4 (`ReturnType`, `ResultIsFlat`, `PreservesOrder`, `NonNegativeLength`) | 2 (`IsList`, `NoNestedLists`) |
| Case çeşitliliği | strings_not_recursed, dicts_kept_as_is, list_with_none_elements, list_with_booleans, floats_nested, triple_nested | Benzer kapsamda ama daha az |
| Error case kalitesi | Temiz, tekrarsız 7 raises | **Ciddi sorunlar** (aşağıda) |

Flash'in spec'inde **3 kritik sorun** var:

1. **Yanlış assertion**: `other_containers_as_atoms` case'i `output == [[1, 2], {'a': 1}]` diyor — yani flatten'ın HİÇ BİR ŞEYİ düzleştirmemesini bekliyor. Doğrusu `[1, 2, {'a': 1}]` olmalı. **Semantik hata.**

2. **Tekrar eden error case'ler**: `null_input_error` ve `verified_error_none` aynı test. `int_input_error` ve `verified_error_int` aynı test. Toplamda **5 duplikat error case** var.

3. **Sahte error case**: `verified_error_tuple` → `input: null, assertion: "True", raises: TypeError` — anlamsız bir case, sadece yer kaplıyor.

#### levenshtein

**Opus**: 42 case, 9 raises, 0 refine, 100%, 92.1s
**Flash**: 23 case, 3 raises, 0 refine, 100%, 10.9s

Her ikisi de geçti ama kalite farkı dev:

| Boyut | Opus | Flash |
|---|---|---|
| Global evaluators | 5 (ReturnType, NonNeg, Upper, Lower, Identity) | 5 (aynı — burada eşit) |
| **Matematiksel özellik testleri** | symmetry_check (forward+reverse), triangle_ineq (3 case), transposition_is_two | Yok |
| Unicode | `café` vs `cafe` testi | Yok |
| Error cases | 9 (none×3, int, list, no_args, one_arg, bool) | 3 (none, int, list) |

Opus'un en etkileyici yanı **matematiksel akıl yürütme**:
- **Simetri**: `levenshtein("kitten","sitting") == levenshtein("sitting","kitten")` — ayrı case'lerle doğrulanıyor
- **Üçgen eşitsizliği**: `d(a,c) <= d(a,b) + d(b,c)` — 3 ilişkili case ile test ediliyor
- **Transpozisyon maliyeti**: `d("ab","ba") == 2` — Levenshtein'ın Damerau-Levenshtein'dan farkını yakalıyor

Flash bu düzeyde kavramsal derinlik göstermiyor.

#### parse_cron (en karmaşık senaryo)

**Opus**: 55 case, 19 raises, 0 refine, 100%, 179.7s
**Flash**: 27 case, 13 raises, 1 refine, 100%, 77.3s

Burada **global evaluator farkı devasa**:

| Opus (9 evaluator) | Flash (3 evaluator) |
|---|---|
| ReturnType(dict) | ReturnType(dict) |
| HasAllKeys (set comparison) | KeyCheck (list order) |
| AllValuesAreSortedLists | — |
| AllValuesAreInts | ValueType (list + int birleşik) |
| MinuteInRange (0-59) | — |
| HourInRange (0-23) | — |
| DayOfMonthInRange (1-31) | — |
| MonthInRange (1-12) | — |
| DayOfWeekInRange (0-6) | — |

Opus **her field için bağımsız range validation** ekliyor. Bu, mutation testing'de fark yaratacak düzeyde bir yapısal güvence. Bir mutant minute'ü 60 yapsa bile Opus'un spec'i yakalar; Flash'inki yakalamaz.

Opus'un spec'i ayrıca **bölümlere ayrılmış**: `TYPICAL CASES`, `ALL WILDCARDS`, `BOUNDARY CASES`, `EDGE CASES`, `ERROR CASES` — yorumlarla organize edilmiş, okunabilir.

---

### 3. Sonuçlar ve Trade-off Analizi

**Opus'un gerçek avantajları:**
1. **Zero-shot reliability** — refinement loop'a hiç girmeden 100% ulaşıyor. Bu hem zaman tasarrufu hem de "spec'in ilk halinden zaten doğru olması" anlamına geliyor.
2. **Global evaluator zenginliği** — özellikle parse_cron'da (9 vs 3), spec'in bir "bug detektörü" olarak gücü çok daha yüksek.
3. **Matematiksel kavram testleri** — simetri, üçgen eşitsizliği, transpozisyon gibi algoritmanın yapısal özelliklerini test ediyor.
4. **Temiz error case'ler** — duplikat yok, sahte case yok, anlamlı `match` pattern'leri.
5. **Semantik doğruluk** — Flash'in yanlış assertion yazdığı yerde (other_containers_as_atoms), Opus böyle hatalar yapmıyor.

**Flash'in avantajı:**
- **Hız**: 2.65x daha hızlı
- **Maliyet**: ~100x daha ucuz (token fiyat farkı + daha az token kullanımı)
- Levenshtein'ı 10.9s'de bitirdi (Opus 92.1s)

**Karar noktası:** Flash, "geçti/kaldı" açısından genellikle yeterli ama spec *kalitesi* tartışılmaz şekilde düşük. Opus'un ürettiği spec bir gerçek regresyon test suite'i gibi çalışabilir; Flash'inki daha çok bir "smoke test." Mutation testing yapsak aradaki fark muhtemelen dramatik olur.

**Öneri:** Opus'u varsayılan model yapmak maliyet açısından mantıksız. Ama **critical path'teki fonksiyonlar** (payment, auth, parsing logic gibi) için Opus kesinlikle değer. Hibrit yaklaşım: **lite exploration + Opus spec generation** hâlâ en mantıklı rota.