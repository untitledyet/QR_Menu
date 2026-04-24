() => {
  // Step 1: Get category names from the sidebar nav (data-testid="list-item-...")
  var catNames = [];
  var navItems = document.querySelectorAll('[data-testid^="list-item-"]');
  for (var i = 0; i < navItems.length; i++) {
    var t = navItems[i].textContent.trim();
    if (t && t.length > 1 && t.length < 80) catNames.push(t);
  }

  // Step 2: Find category section headers that match nav names
  // These are the real category dividers in the page
  var catSet = {};
  for (var i = 0; i < catNames.length; i++) catSet[catNames[i]] = true;

  // Step 3: Walk through all product-rows, determine category by
  // finding the nearest preceding element whose text matches a category name
  var results = {};
  var currentCat = catNames.length > 0 ? catNames[0] : 'Menu';

  // Get all elements in order - look for category markers and product rows
  var allElements = document.querySelectorAll('h2, [data-testid="product-row"]');
  for (var i = 0; i < allElements.length; i++) {
    var el = allElements[i];

    if (el.tagName === 'H2') {
      var txt = el.textContent.trim();
      // Only treat as category if it matches a nav item
      if (catSet[txt]) {
        currentCat = txt;
        if (!results[currentCat]) results[currentCat] = [];
      }
      continue;
    }

    // product-row
    var lines = (el.innerText || '').split('\n').map(function(l){return l.trim();}).filter(function(l){return l;});
    var name = '';
    var price = '';
    var desc = '';
    for (var j = 0; j < lines.length; j++) {
      if (lines[j].match(/\d+[,.]\d{2}[₾]/)) {
        price = lines[j];
      } else if (!name) {
        name = lines[j];
      } else if (!desc && lines[j].length > 2) {
        desc = lines[j];
      }
    }
    var img = el.querySelector('img');
    var imgSrc = img ? (img.getAttribute('src') || '') : '';
    if (name) {
      if (!results[currentCat]) results[currentCat] = [];
      results[currentCat].push({name: name, price: price, description: desc, image: imgSrc});
    }
  }

  return results;
}
