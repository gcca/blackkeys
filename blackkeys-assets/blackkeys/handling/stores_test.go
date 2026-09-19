package handling

import (
	"testing"

	"github.com/plaza-san-miguel/blackkeys/blackkeys-assets/samples"
)

func TestLoadStoresMapsEmbeddedSnapshot(t *testing.T) {
	stores, err := decodeStores(samples.StoresParquet)
	if err != nil {
		t.Fatalf("decodeStores: %v", err)
	}

	if len(stores) != 318 {
		t.Fatalf("got %d stores, want 318", len(stores))
	}
	if stores[0].GetName() != "ADIDAS" {
		t.Errorf("got first store %q, want %q", stores[0].GetName(), "ADIDAS")
	}
}

func TestLoadStoresMapsNestedRecords(t *testing.T) {
	stores, err := decodeStores(samples.StoresParquet)
	if err != nil {
		t.Fatalf("decodeStores: %v", err)
	}

	first := stores[0]
	if got := first.GetId(); got != 81 {
		t.Errorf("got id %d, want 81", got)
	}
	if got := first.GetSubcategory().GetName(); got != "Deportes y Outdoor" {
		t.Errorf("got subcategory %q, want %q", got, "Deportes y Outdoor")
	}
	if got := first.GetSubcategory().GetCategory().GetName(); got != "Tiendas por departamento" {
		t.Errorf("got category %q, want %q", got, "Tiendas por departamento")
	}
	if got := len(first.GetStores()); got != 1 {
		t.Fatalf("got %d locations, want 1", got)
	}
	if got := first.GetStores()[0].GetLocation().GetName(); got != "Corredor Mantaro, 2do nivel" {
		t.Errorf("got location %q, want %q", got, "Corredor Mantaro, 2do nivel")
	}
}

func TestLoadStoresMapsNullStorePhotoToEmptyString(t *testing.T) {
	stores, err := decodeStores(samples.StoresParquet)
	if err != nil {
		t.Fatalf("decodeStores: %v", err)
	}

	byName := make(map[string]string, len(stores))
	for _, store := range stores {
		byName[store.GetName()] = store.GetStorePhoto()
	}

	for _, name := range []string{"BCP", "Dollarcity", "Otto Grill"} {
		photo, ok := byName[name]
		if !ok {
			t.Fatalf("store %q missing from the snapshot", name)
		}
		if photo != "" {
			t.Errorf("store %q: got storePhoto %q, want empty string", name, photo)
		}
	}
}
