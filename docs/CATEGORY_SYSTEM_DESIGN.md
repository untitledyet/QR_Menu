# Category & Subcategory System — Design Doc

> **სტატუსი:** ცვლილებები ამ დოკუმენტიდან არ არის გამოყენებული.
> **მიზანი:** Global taxonomy + per-venue customization, ისე რომ ყველა მენიუ თანმიმდევრულად დააწყოს, მაგრამ ყოველ რესტორანს თავისი მოქნილობა ჰქონდეს.

---

## 1. ამჟამინდელი მდგომარეობის რეალობა

### Schema (რა გვაქვს)

**Global layer** (Tably-platform-wide):
- `GlobalCategory` (id, name, name_en, icon, sort_order, is_active)
- `GlobalSubcategory` (id, category_id, name, name_en, is_active)
- `GlobalItem` (id, category_id, subcategory_id, name_ge, ...) — references global cats

**Venue layer** (per-restaurant):
- `Category` (CategoryID, CategoryName, CategoryName_en, venue_id, group_id)
- `Subcategory` (SubcategoryID, SubcategoryName, CategoryID)
- `FoodItem` (FoodItemID, CategoryID, SubcategoryID, ...)

### კრიტიკული აღმოჩენა (DB inspection-დან)

```
TOTAL: cats=0, subs=0, items=256
```

🔴 **256 GlobalItem არის, მაგრამ 0 GlobalCategory და 0 GlobalSubcategory.**

ყველა item NULL category_id-ით ცხოვრობს. AI auto-classification (`assign_global_categories`) ცარიელ სიას აბრუნებს — ფუნქცია ფაქტობრივად არ მუშაობს. ეს არის foundation rebuild-ის წერტილი.

### რა-რა მუშაობს და არ მუშაობს

| ფუნქცია | სტატუსი | კომენტარი |
|---|---|---|
| Venue admin ქმნის `Category` | ✅ მუშაობს | freeform — ყოველი რესტორანი ცარიელი ფურცლიდან იწყებს |
| Venue admin ქმნის `Subcategory` | ✅ მუშაობს | category-ში nested |
| AI კერძს ხვდება global category-ში | ❌ მუშაობს | global cats ცარიელია |
| AI იაზრებს subcategory-ს | ❌ არ მუშაობს | global subs ცარიელია |
| Menu import-ი ქმნის venue category-ებს | ✅ მუშაობს | მაგრამ AI-ს ნაგროვები სახელები ერთი მენიუდან მეორეში არ ემთხვევა (ერთს "სალათები", მეორეს "Salads") |
| Group-shared კატეგორიები | ✅ schema მზადაა | code რომ ფლობს — საჭიროებს check |
| Venue-ს მიანებოს global category-ის override | ❌ არ არსებობს | schema არ აქვს |
| Venue-ს დაუმალოს კატეგორია | ❌ არ არსებობს | მხოლოდ delete |
| Venue-ს თავისი sort_order | ❌ არ არსებობს | DB id თანმიმდევრობით |

---

## 2. პრობლემის სტრუქტურა

### პრობლემა 1: ცხოვრება სტანდარტი
ყოველი რესტორანი ცარიელი ფურცლიდან იწყებს. Owner-ი თვითონ გადაწყვეტს რა category უწოდოს ხინკალს. შედეგი:
- ერთ რესტორანში "ცხელი კერძები" → ხინკალი
- მეორეში "ხინკალი" თვითონ კატეგორიაა
- მესამეში "ქართული სამზარეულო" → ხინკალი
- AI ვერ ხვდება — ყოველი მენიუ უნიკალური structure-ით

### პრობლემა 2: ცვლილების მართვა
როცა Tably "სალათები" ქართულ category-ად დაამატებს, ეს ცვლილება არსებულ რესტორნებს არ ეხება. მათ უკვე "Salads" აქვთ ხელით. მომავალი გადაწყვეტილებები რთული ხდება.

### პრობლემა 3: დუბლირება და ჯანდაბა
- რესტორანს თვითონ ხატავს ყველა category-ს
- AI auto-import-ზე ქმნის ახალ category-ს ყოველ ჯერზე
- შედეგი: 1 რესტორანში 4 category "სალათი" / "სალათები" / "Salads" / "Salad"

### პრობლემა 4: მოქნილობა vs სტანდარტი
- სტანდარტი მინდა — საერთო taxonomy ყველა რესტორანისთვის (ანალიტიკა, library matching)
- მოქნილობა მინდა — ერთ რესტორანს არ უნდა "სუპები", მეორეს არ უნდა "ალკოჰოლი", მესამეს მხოლოდ კოქტეილები აქვს

---

## 3. შემოთავაზებული არქიტექტურა

### სამი ფენა

```
┌─────────────────────────────────────────────────────────────┐
│  Layer 1: GLOBAL MASTER TAXONOMY (Tably ქმნის და ფლობს)    │
│  • 12-15 კატეგორია, ყოველს 3-8 ქვე-კატეგორია               │
│  • ka/en/ru                                                 │
│  • icon, sort order                                         │
│  • ბმები: GlobalItem -> GlobalCategory                      │
│  • წყარო: Tably superadmin                                  │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       │  inherit + override
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  Layer 2: VENUE OVERRIDE TABLE                               │
│  VenueCategoryOverride:                                      │
│    venue_id + global_category_id                             │
│    is_hidden (boolean)                                       │
│    custom_name_ka, custom_name_en (optional)                 │
│    custom_icon (optional)                                    │
│    custom_sort_order (optional)                              │
│                                                              │
│  Resolution:                                                 │
│    venue's view = (global cats) - (hidden) + custom override │
│                 + venue-specific custom Categories           │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  Layer 3: VENUE-ONLY CUSTOM CATEGORIES                       │
│  Category.venue_id IS NOT NULL AND global_category_id IS NULL│
│  • რესტორნის-სპეციფიკური ("Lunch box", "Chef's special")    │
│  • არცერთ global-ში არ არსებობს                              │
│  • ცხოვრობს მხოლოდ ამ რესტორანში                            │
└─────────────────────────────────────────────────────────────┘
```

### Schema ცვლილებები

```sql
-- Категория-ში link რომელიც global-ს ეხება (NULL = pure venue custom)
ALTER TABLE Categories ADD COLUMN global_category_id INTEGER REFERENCES GlobalCategories(id);
ALTER TABLE Categories ADD COLUMN sort_order INTEGER DEFAULT 0;
ALTER TABLE Categories ADD COLUMN is_hidden BOOLEAN DEFAULT FALSE;

ALTER TABLE Subcategories ADD COLUMN global_subcategory_id INTEGER REFERENCES GlobalSubcategories(id);
ALTER TABLE Subcategories ADD COLUMN sort_order INTEGER DEFAULT 0;
ALTER TABLE Subcategories ADD COLUMN is_hidden BOOLEAN DEFAULT FALSE;

-- Venue type → preset mapping (cafe / restaurant / bar / fast-food)
ALTER TABLE Venues ADD COLUMN venue_type VARCHAR(30) DEFAULT 'restaurant';

-- Index
CREATE INDEX idx_categories_global ON Categories(global_category_id);
```

### ნაბიჯი-ნაბიჯ resolution algorithm

```python
def get_venue_categories(venue_id):
    """რა category უნდა ნახოს ამ რესტორნის customer-მა."""
    # 1. ყველა category რომელიც ამ venue-ისთვის არის შექმნილი
    venue_cats = Category.query.filter_by(venue_id=venue_id, is_hidden=False).all()
    
    # 2. დაასორტირე: custom sort_order > global sort_order
    venue_cats.sort(key=lambda c: (
        c.sort_order if c.sort_order else (
            c.global_category.sort_order if c.global_category else 999
        )
    ))
    
    return venue_cats
```

ანუ ფაქტობრივად:
- `Category` cabin-ი არსებობს ყოველ venue-ისთვის
- თუ `global_category_id` სავსეა → ეს არის "instance" global კატეგორიის
- თუ NULL → custom venue-only

---

## 4. სტანდარტი — Global Taxonomy (proposed)

ქართული რესტორნის სტანდარტული სტრუქტურა, რომელიც 90%+ რესტორანს ფარავს:

### ცხელი კერძები — Hot Dishes
- ხინკალი — Khinkali
- მცხვადი — Mtsvadi (BBQ)
- ქათამი — Chicken
- ღორი — Pork
- ხბო — Veal
- კერძები ქვაბში — Pottery dishes (ჭანახი, ოჯახური)
- ფილე და სტეიკი — Steaks & Fillets

### ცომეული — Bread & Pastries
- ხაჭაპური — Khachapuri
- ლობიანი — Lobiani
- მჭადი — Mchadi
- პური — Bread
- სხვა ცომეული — Other pastries

### სუპები — Soups
- ხარჩო — Kharcho
- ჩიხირთმა — Chikhirtma
- ბორში — Borsch
- ცივი სუპი — Cold soups
- სხვა სუპები — Other soups

### სალათები — Salads
- ქართული სალათი — Georgian salad
- სეზონური სალათი — Seasonal
- პრემიუმ სალათი (Caesar, Greek) — Premium
- ცხელი სალათი — Warm salads

### ცივი კერძები & წახემსები — Cold Dishes & Appetizers
- ფხალი — Pkhali
- ბადრიჯანი — Eggplant rolls
- ყველის ასორტი — Cheese platter
- კარპაჩო, ტატარი — Carpaccio, Tartare
- სხვა წახემსები — Other appetizers

### პასტა და რიზოტო — Pasta & Risotto
- პასტა — Pasta
- რიზოტო — Risotto
- ლაზანია — Lasagna

### პიცა — Pizza

### ბერგერი და სენდვიჩი — Burgers & Sandwiches
- ბერგერი — Burgers
- სენდვიჩი — Sandwiches
- შაურმა — Shaurma
- ჰოთ-დოგი — Hot dogs

### სუშები — Sushi & Asian
- როლი — Rolls
- სუშები — Sushi
- სხვა აზიური — Other Asian (rāmen, pad thai)

### დესერტი — Desserts
- ნაყინი — Ice cream
- ნამცხვარი — Cakes
- ქართული ტრადიციული — Traditional Georgian (ჩურჩხელა, თათარა)
- ცომეული დესერტი — Pastry desserts

### სასმელი — Drinks
- წყალი — Water
- ლიმონათი — Lemonades & soft drinks
- წვენი ფრეშ — Fresh juice
- ცხელი სასმელები (ყავა, ჩაი) — Hot drinks

### ალკოჰოლი — Alcohol
- ღვინო წითელი — Red wine
- ღვინო თეთრი — White wine
- ჭაჭა — Chacha
- ლუდი — Beer
- კოქტეილი — Cocktails
- სხვა ალკოჰოლი — Spirits

### ბავშვის მენიუ — Kids Menu

### სპეციალური — Specials
- შეფის სპეციალი — Chef's special
- ვეგანური — Vegan
- გლუტენ-ფრი — Gluten-free

**Total: 14 ძირითადი კატეგორია, ~70 ქვეკატეგორია.**

---

## 5. Venue Onboarding Flow — როგორ იღებს რესტორანი თავის სტრუქტურას

### Option A: **Preset by venue type** (რეკომენდირებული)

რეგისტრაციისას ერჩევა:

```
┌──────────────────────────────────────────────┐
│  რა ტიპის ობიექტია?                          │
│                                              │
│  ○ რესტორანი (full menu)                    │
│  ○ კაფე / ბრანჩი                            │
│  ○ ბარი / პაბი                               │
│  ○ ფასტ-ფუდი                                 │
│  ○ პიცერია                                   │
│  ○ სუშები                                    │
│  ○ ცარიელი (მე გავაკეთებ)                   │
└──────────────────────────────────────────────┘
```

ყოველ ტიპს თავისი preset:

| Type | მოყვება |
|---|---|
| **რესტორანი** | ცხელი კერძები, ცომეული, სუპები, სალათები, ცივი კერძები, დესერტი, სასმელი, ალკოჰოლი |
| **კაფე** | სალათები, სენდვიჩი, ცომეული, დესერტი, სასმელი, ცხელი სასმელი |
| **ბარი** | ცივი წახემსები, ბერგერი, ალკოჰოლი (ყველა sub), სასმელი, კოქტეილი |
| **ფასტ-ფუდი** | ბერგერი, შაურმა, პიცა, კარტოფილი, სასმელი |
| **პიცერია** | პიცა (ქვე-ტიპები), პასტა, სალათები, სასმელი |
| **სუშები** | სუშები (ყველა sub), როლი, აზიური, სასმელი |
| **ცარიელი** | არცერთი — owner-ი თვითონ ამატებს |

### Option B: **Free-form** (ყოველი category ცარიელი ფურცლიდან)
- ხანდახან საჭიროა ექსპერიმენტული რესტორნებისთვის
- ✅ flexible
- ❌ no standardization

**ჩემი რჩევა:** **Option A** default, **Option B** "advanced" tab-ში.

---

## 6. Venue Admin UX — როგორ ცვლის თავის category-ებს

### Backoffice screen: `Settings → Menu Categories`

```
┌────────────────────────────────────────────────────────────────┐
│  მენიუს კატეგორიები                                           │
│  ─────────────────────────────────────────────────────────    │
│                                                                │
│  [ ↻ Reset to default ] [ + Add custom category ]            │
│                                                                │
│  ⠿ ☑ ცხელი კერძები          [Edit name] [↑ Hide] (12 items) │
│      ⠿ ☑ ხინკალი             [Edit] [Hide] (3 items)         │
│      ⠿ ☑ მცხვადი              [Edit] [Hide] (5 items)         │
│      ⠿ ☐ ქათამი (hidden)     [Show]                          │
│      ⠿ ☑ ღორი                 [Edit] [Hide] (4 items)         │
│      [+ ქვეკატეგორიის დამატება]                              │
│                                                                │
│  ⠿ ☑ ცომეული                  [Edit name] [↑ Hide] (8 items) │
│      ⠿ ☑ ხაჭაპური             [Edit] [Hide] (5 items)         │
│      ⠿ ☑ ლობიანი              [Edit] [Hide] (3 items)         │
│                                                                │
│  ⠿ ☑ ჩემი სპეციალი ★ custom   [Edit name] [Delete] (6 items)│
│                                                                │
│  ⠿ ☐ ალკოჰოლი (hidden)        [Show]                          │
└────────────────────────────────────────────────────────────────┘
```

### Owner-ის შესაძლებელი action-ები

| Action | რა ხდება DB-ში | Reversible? |
|---|---|---|
| **Hide global category** | `Category.is_hidden = TRUE` | ✅ Show-ით უკან |
| **Rename category** | `Category.CategoryName` ცვლის (override) | ✅ Reset → default |
| **Reorder** | `Category.sort_order` change | ✅ |
| **Add subcategory** | new row in `Subcategories` | ✅ |
| **Add custom category** | `Category` row, `global_category_id = NULL` | ✅ |
| **Delete custom category** | row delete + items orphaned | ❌ items უნდა გადაიტანო |
| **"Reset to default"** | წაშალე ყველა override, აღადგინე preset | ✅ |

### კრიტიკული წესები

1. **Items-ის dangling-ისგან დაცვა:** category წაშლისას — თუ items არიან, აიძულე owner რომ ჯერ გადაიტანოს ან დაარქივოს
2. **Hidden ≠ Deleted:** hide-ი არ ცვლის item-ებს. Show-ით ისევ ჩანს.
3. **Custom rename ≠ global rename:** owner რომ "ცხელი კერძები" "Hot Stuff"-ად ცვლის, ამას არცერთი სხვა რესტორანი ვერ ხედავს.
4. **Global update propagation:** Tably ცვლის "ცხელი კერძები" → "ცხელი" — venue ხედავს default-ად, **მაგრამ თუ override აქვს, override-ი რჩება**.

---

## 7. AI Auto-Classification — გადააწყობა

ახლა (broken):
```
AI parses menu → assigns to GlobalCategory.name → 0 results (cats are empty)
```

შემდგომ:
```
1. AI parses menu items (current flow)
2. assign_global_categories(items, GLOBAL_TAXONOMY)
   → ყოველი item-ი ხვდება global cat + sub-ში
3. import_into_venue(venue_id, items)
   → ყოველი global cat-ს, რომელიც item-ებში გვხვდება:
       - თუ venue-ში უკვე არსებობს ამ global_cat-ის Category → reuse
       - თუ არა → ავტომატურად შექმენი (Category-ი global_category_id-თ)
   → იმავე ლოგიკით subcategory
   → FoodItem.CategoryID ↦ ახალი/არსებული Category.CategoryID
4. Owner ხედავს preview-ს, შეუძლია reorganize-ი save-მდე
```

### Edge cases
- **Item-ი არცერთ global cat-ს არ ხვდება** → fallback "სხვა" ან AI-ს custom suggestion ("Cold pressed juices" — ახალი category-ის შეთავაზება superadmin-ისთვის)
- **Venue-ს default-ად არ აქვს ალკოჰოლი (cafe preset)** → AI find-ებს wine-ს → უნდა ვცადოთ category უხილავიდან გავხსნათ ან ცალკე custom Category-ად შევქმნათ
- **Custom venue category** → ახალი menu import-ი ვერ აღმოჩენს, AI ხედავს მხოლოდ global taxonomy-ს

---

## 8. Migration Plan — ნაბიჯ-ნაბიჯ

### Phase 1: **Foundation (1-2 დღე)**

- [ ] **T1.1** Schema migration — Categories/Subcategories-ში დაამატე `global_category_id`, `sort_order`, `is_hidden`
- [ ] **T1.2** `Venue.venue_type` column-ი + default 'restaurant'
- [ ] **T1.3** Seed script — 14 GlobalCategory + ~70 GlobalSubcategory (§4-დან) ka/en/icon-ით
- [ ] **T1.4** Validate: 256 არსებული GlobalItem-ი ხელით ან AI-ით assign global category-ის
- [ ] **T1.5** Backfill — ყოველი არსებული `Category` → `global_category_id`-ის auto-resolve fuzzy name match-ით (ხელით review-სთვის)

### Phase 2: **Resolution layer (2-3 დღე)**

- [ ] **T2.1** `app/services/category_service.py` — `get_venue_categories()`, `get_venue_subcategories(category_id)`, with override resolution
- [ ] **T2.2** Customer menu render-ი ამ სერვისით (`menu_routes.py` refactor)
- [ ] **T2.3** Venue admin item form — categories dropdown ამ სერვისიდან
- [ ] **T2.4** Group menu inheritance — group-shared categories (უკვე schema მზადაა, სერვისს დავამატოთ)

### Phase 3: **Onboarding presets (1-2 დღე)**

- [ ] **T3.1** `VENUE_TYPE_PRESETS` dict — venue_type → list of global_category_ids
- [ ] **T3.2** Registration flow-ში venue type არჩევანი
- [ ] **T3.3** `seed_venue_categories(venue_id, venue_type)` — preset-ის გადატანა
- [ ] **T3.4** Existing venue-ებზე "Apply preset" button (one-time tool)

### Phase 4: **Backoffice UI (3-4 დღე)**

- [ ] **T4.1** New page `Settings → Menu Categories` (drag-drop, hide toggle, rename inline)
- [ ] **T4.2** Subcategory nested editing
- [ ] **T4.3** "Reset to default" button (clears overrides, re-applies preset)
- [ ] **T4.4** "Add custom category" modal
- [ ] **T4.5** Item-orphan check — category წაშლა blocked თუ items არიან, "Move items to..." dropdown
- [ ] **T4.6** SortableJS-ით drag-drop (frontend)

### Phase 5: **AI rewire (1-2 დღე)**

- [ ] **T5.1** `assign_global_categories` რეფაქტორი — global taxonomy-ს ფაქტობრივად იყენებდეს
- [ ] **T5.2** Menu import flow-ში — venue-ში არ არსებული global category → auto-create with `global_category_id`
- [ ] **T5.3** Hidden cat-ში item-ი ხვდება → `is_hidden=False` reset prompt owner-ს
- [ ] **T5.4** "Suggest new global category" — AI-მ rare item-ი ვერ მოარგო → superadmin queue

### Phase 6: **Polish (1-2 დღე)**

- [ ] **T6.1** Analytics dashboard — superadmin ხედავს რომელ global category-ში რამდენი venue, რამდენი item, რამდენი hidden
- [ ] **T6.2** Bulk tools — "კატეგორიის გადარქმევა ყველა venue-ში" (broadcast rename)
- [ ] **T6.3** Documentation — owner-help docs ქართულად
- [ ] **T6.4** Sentry-ში alerts — category orphan rate, hidden rate

**Total: ~10-15 working days, solo.**

---

## 9. Decision Matrix — Trade-off-ები

### რატომ Layer 2 override (Option B) და არა pure copy (Option A)?

| ფაქტორი | Option A (copy) | **Option B (override)** | Option C (hybrid) |
|---|---|---|---|
| Global update propagation | ❌ | ✅ | ⚠ opt-in |
| Schema simplicity | ✅ ცვლილება არ უნდა | ⚠ migration | ⚠ migration |
| Venue freedom | ✅ | ✅ | ✅ |
| Cross-venue analytics | ❌ ცუდი normalization | ✅ | ⚠ |
| AI matching | ⚠ duplicate cats per venue | ✅ stable taxonomy | ⚠ |
| Implementation effort | 1 კვირა | **2 კვირა** | 2-3 კვირა |
| Long-term maintainability | ❌ data drift | ✅ | ⚠ |

**Verdict: Option B** — 1 კვირა მეტი ინვესტიცია, 2 წელი მაღალი dividend.

### რატომ ცალკე Categories table-ში override და არა ცალკე VenueCategoryOverride?

დიახ, თეორიულად VenueCategoryOverride join table უფრო "სწორია". მაგრამ:

| ფაქტორი | ცალკე override table | **Categories-ში global_category_id** |
|---|---|---|
| Custom venue cats-ის storage | სხვა table | იმავე table-ში (NULL global_id) |
| Query simplicity | 2-table JOIN | 1 table |
| FoodItem.CategoryID ისევ მუშაობს | ✅ | ✅ |
| Migration complexity | high | medium |

**Verdict: Categories-ში global_category_id** — code path ერთია, FoodItem-ი ყოველთვის venue Category-ს ეხება.

---

## 10. რისკები და mitigation

| რისკი | Mitigation |
|---|---|
| Existing 0 GlobalCategories — ყველა იმპორტი დაიშლება | Phase 1.3 seed უნდა იყოს Phase 2-ის წინ აუცილებლად |
| 256 GlobalItem orphan — ხელით assignment დიდი სამუშაოა | AI batch assign script (10 წთ) → manual review |
| Existing venue-ები ცხოვრობენ წინა schema-თი | Backfill script ყოველი არსებული Category-ს `global_category_id`-ს fuzzy match-ით |
| Owner-ი დაიკარგება UI-ში | "Reset to default" ღილაკი ყოველთვის ცხადად ხილული |
| Performance — ყოველ menu render-ზე override resolution | DB index-ი + Redis cache 5min |
| Hidden category-ში item-ის შესვლა | Validation — Importer-ი მონიშნავს, owner-ს გამოუჩნდება warning |

---

## 11. Open Questions (გადაწყვეტამდე)

- [ ] **Q1.** Group-შიდა category sharing — ჯგუფის ყველა ფილიალი ერთ category-ს ხედავს, თუ ცალკე? (Schema მზადაა, semantic გადაწყვეტა საჭიროა)
- [ ] **Q2.** Multi-language — owner-ი ცვლის name_ka, name_en ავტომატურად ითარგმნოს AI-ით თუ ხელით უნდა შეავსოს?
- [ ] **Q3.** Custom subcategory პრევენცია — owner ცდილობს subcategory-ს დაამატოს global category-ში? OK ?
- [ ] **Q4.** Image/icon — venue-ს თავისი icon შეუძლია upload-ი თუ მხოლოდ FontAwesome list-დან?
- [ ] **Q5.** Sort order — კატეგორიული global, ან ცალკე per-venue? (პასუხი: per-venue override, default global)
- [ ] **Q6.** Customer-ფრონტენდი — empty category უნდა ჩანდეს რომელიც item-ი არ აქვს? (პასუხი: არ ჩანდეს)

---

## 12. დღევანდელი 3 ნაბიჯი (გადაწყვეტამდე ინსპექცია)

1. **256 GlobalItem-ი ხელით გადახედე** — რა ტიპის item-ებია? იქედან გამომდინარე taxonomy-ს დავაზუსტოთ
2. **5-10 არსებული venue-ის category list ნახე** (production DB) — ნახე რა pattern-ები არსებობს
3. **გადაწყვეტ — Option A (copy) vs Option B (override)?** — ეს ცვლის Phase 1.1-ის migration
