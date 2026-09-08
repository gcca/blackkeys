package handling

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/bradfitz/gomemcache/memcache"
	"github.com/plaza-san-miguel/blackkeys/blackkeys-assets/blackkeys/storage"
	assetsv1 "github.com/plaza-san-miguel/blackkeys/blackkeys-assets/gen/assetsv1"
	"github.com/plaza-san-miguel/blackkeys/blackkeys-assets/samples"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
	"google.golang.org/protobuf/proto"
)

type fakeBrandsCache struct {
	getItem  *memcache.Item
	getErr   error
	setErr   error
	setItem  *memcache.Item
	getCalls int
	setCalls int
}

func (c *fakeBrandsCache) Get(string) (*memcache.Item, error) {
	c.getCalls++
	return c.getItem, c.getErr
}

func (c *fakeBrandsCache) Set(item *memcache.Item) error {
	c.setCalls++
	c.setItem = item
	return c.setErr
}

type fakeImageStore struct {
	data        []byte
	contentType string
	err         error
	calls       []string
}

func (f *fakeImageStore) GetImage(_ context.Context, key string) ([]byte, string, error) {
	f.calls = append(f.calls, key)
	return f.data, f.contentType, f.err
}

func testBrandsService(cache brandsCache) *BrandsService {
	return newBrandsService([]*assetsv1.Brand{{Name: "snapshot"}}, cache, nil)
}

func testBrandsServiceWithImages(images imageStore) *BrandsService {
	return newBrandsService([]*assetsv1.Brand{{Name: "snapshot"}}, nil, images)
}

func TestLoadBrandsMapsEmbeddedSnapshot(t *testing.T) {
	brands, err := decodeBrands(samples.BrandsParquet)
	if err != nil {
		t.Fatalf("decodeBrands: %v", err)
	}

	if len(brands) != 318 {
		t.Fatalf("got %d brands, want 318", len(brands))
	}
	if brands[0].GetName() != "barletto" {
		t.Errorf("got first brand %q, want %q", brands[0].GetName(), "barletto")
	}
	if brands[0].GetDisplayName() != "Barletto" {
		t.Errorf("got first brand display name %q, want %q", brands[0].GetDisplayName(), "Barletto")
	}
}

func TestLoadBrandsMapsNestedRecords(t *testing.T) {
	brands, err := decodeBrands(samples.BrandsParquet)
	if err != nil {
		t.Fatalf("decodeBrands: %v", err)
	}

	first := brands[0]
	if got := first.GetKioskId(); got != 19 {
		t.Errorf("got kiosk id %d, want 19", got)
	}
	if got := len(first.GetStores()); got != 1 {
		t.Fatalf("got %d stores, want 1", got)
	}
	if got := first.GetStores()[0].GetName(); got != "Boulevard Plaza Mantaro, 1er nivel" {
		t.Errorf("got store %q, want %q", got, "Boulevard Plaza Mantaro, 1er nivel")
	}

	amenities := make(map[string]string, len(first.GetAmenities()))
	for _, amenity := range first.GetAmenities() {
		amenities[amenity.GetName()] = amenity.GetValue()
	}
	if got := amenities["phone"]; got != "(+51) 988 373 737" {
		t.Errorf("got phone amenity %q, want %q", got, "(+51) 988 373 737")
	}
	if got := amenities["website"]; got != "https://www.barletto.com.pe/" {
		t.Errorf("got website amenity %q, want %q", got, "https://www.barletto.com.pe/")
	}

	wantTags := []string{"comida", "helados", "postres", "cafeterias"}
	if len(first.GetTags()) != len(wantTags) {
		t.Fatalf("got %d tags, want %d", len(first.GetTags()), len(wantTags))
	}
	for i, tag := range wantTags {
		if first.GetTags()[i] != tag {
			t.Errorf("tag %d: got %q, want %q", i, first.GetTags()[i], tag)
		}
	}
}

func TestLoadBrandsMapsEmptyStoresList(t *testing.T) {
	brands, err := decodeBrands(samples.BrandsParquet)
	if err != nil {
		t.Fatalf("decodeBrands: %v", err)
	}

	byName := make(map[string]int, len(brands))
	for _, brand := range brands {
		byName[brand.GetName()] = len(brand.GetStores())
	}

	for _, name := range []string{"freezyderm", "dollarcity"} {
		count, ok := byName[name]
		if !ok {
			t.Fatalf("brand %q missing from the snapshot", name)
		}
		if count != 0 {
			t.Errorf("brand %q: got %d stores, want 0", name, count)
		}
	}
}

func TestListReturnsCachedResponse(t *testing.T) {
	value, err := proto.Marshal(&assetsv1.ListResponse{Brands: []*assetsv1.Brand{{Name: "cached"}}})
	if err != nil {
		t.Fatalf("Marshal: %v", err)
	}
	cache := &fakeBrandsCache{getItem: &memcache.Item{Value: value}}

	response, err := testBrandsService(cache).List(t.Context(), &assetsv1.ListRequest{})
	if err != nil {
		t.Fatalf("List: %v", err)
	}
	if got := response.GetBrands()[0].GetName(); got != "cached" {
		t.Errorf("brand name: got %q, want cached", got)
	}
	if cache.setCalls != 0 {
		t.Errorf("Set calls: got %d, want 0", cache.setCalls)
	}
}

func TestListCachesSnapshotResponse(t *testing.T) {
	cache := &fakeBrandsCache{getErr: memcache.ErrCacheMiss}

	response, err := testBrandsService(cache).List(t.Context(), &assetsv1.ListRequest{})
	if err != nil {
		t.Fatalf("List: %v", err)
	}
	if got := response.GetBrands()[0].GetName(); got != "snapshot" {
		t.Errorf("brand name: got %q, want snapshot", got)
	}
	if cache.setCalls != 1 {
		t.Fatalf("Set calls: got %d, want 1", cache.setCalls)
	}
	if cache.setItem.Key != brandsListCacheKey {
		t.Errorf("cache key: got %q, want %q", cache.setItem.Key, brandsListCacheKey)
	}
	if cache.setItem.Expiration != int32(brandsListCacheTTL/time.Second) {
		t.Errorf("expiration: got %d, want %d", cache.setItem.Expiration, int32(brandsListCacheTTL/time.Second))
	}
	cached := &assetsv1.ListResponse{}
	if err := proto.Unmarshal(cache.setItem.Value, cached); err != nil {
		t.Fatalf("Unmarshal cached response: %v", err)
	}
	if !proto.Equal(cached, response) {
		t.Errorf("cached response does not match response")
	}
}

func TestListFallsBackFromCorruptCachePayload(t *testing.T) {
	cache := &fakeBrandsCache{getItem: &memcache.Item{Value: []byte("corrupt")}}

	response, err := testBrandsService(cache).List(t.Context(), &assetsv1.ListRequest{})
	if err != nil {
		t.Fatalf("List: %v", err)
	}
	if got := response.GetBrands()[0].GetName(); got != "snapshot" {
		t.Errorf("brand name: got %q, want snapshot", got)
	}
	if cache.setCalls != 1 {
		t.Errorf("Set calls: got %d, want 1", cache.setCalls)
	}
}

func TestListFallsBackFromCacheErrors(t *testing.T) {
	for _, tc := range []struct {
		name  string
		cache *fakeBrandsCache
	}{
		{"read", &fakeBrandsCache{getErr: errors.New("read")}},
		{"write", &fakeBrandsCache{getErr: memcache.ErrCacheMiss, setErr: errors.New("write")}},
	} {
		t.Run(tc.name, func(t *testing.T) {
			response, err := testBrandsService(tc.cache).List(t.Context(), &assetsv1.ListRequest{})
			if err != nil {
				t.Fatalf("List: %v", err)
			}
			if got := response.GetBrands()[0].GetName(); got != "snapshot" {
				t.Errorf("brand name: got %q, want snapshot", got)
			}
			if tc.cache.setCalls != 1 {
				t.Errorf("Set calls: got %d, want 1", tc.cache.setCalls)
			}
		})
	}
}

func TestNewBrandsCacheRejectsInvalidNode(t *testing.T) {
	_, err := newBrandsCache([]string{"not a host"}, 1)
	if err == nil {
		t.Fatal("newBrandsCache: want error")
	}
}

func TestValidBrandNameRejectsUnsafeSegments(t *testing.T) {
	for _, tc := range []struct {
		name string
		want bool
	}{
		{"adidas", true},
		{"", false},
		{".", false},
		{"..", false},
		{"a/b", false},
		{"a\\b", false},
		{"a\x00b", false},
	} {
		if got := validBrandName(tc.name); got != tc.want {
			t.Errorf("validBrandName(%q) = %v, want %v", tc.name, got, tc.want)
		}
	}
}

func TestBrandImageKeyMatchesAssetsBoConvention(t *testing.T) {
	if got, want := brandImageKey("adidas", "logo"), "brands/name=adidas/logo.png"; got != want {
		t.Errorf("brandImageKey: got %q, want %q", got, want)
	}
}

func TestLogoReturnsBytesAndContentType(t *testing.T) {
	images := &fakeImageStore{data: []byte("png-bytes"), contentType: "image/png"}
	service := testBrandsServiceWithImages(images)

	response, err := service.Logo(t.Context(), &assetsv1.ImageRequest{Name: "adidas"})
	if err != nil {
		t.Fatalf("Logo: %v", err)
	}
	if string(response.GetData()) != "png-bytes" {
		t.Errorf("data: got %q, want %q", response.GetData(), "png-bytes")
	}
	if response.GetContentType() != "image/png" {
		t.Errorf("content type: got %q, want image/png", response.GetContentType())
	}
	if want := []string{"brands/name=adidas/logo.png"}; len(images.calls) != 1 || images.calls[0] != want[0] {
		t.Errorf("fetched keys: got %v, want %v", images.calls, want)
	}
}

func TestPictureReturnsBytesAndContentType(t *testing.T) {
	images := &fakeImageStore{data: []byte("picture-bytes"), contentType: "image/png"}
	service := testBrandsServiceWithImages(images)

	response, err := service.Picture(t.Context(), &assetsv1.ImageRequest{Name: "adidas"})
	if err != nil {
		t.Fatalf("Picture: %v", err)
	}
	if string(response.GetData()) != "picture-bytes" {
		t.Errorf("data: got %q, want %q", response.GetData(), "picture-bytes")
	}
	if want := []string{"brands/name=adidas/picture.png"}; len(images.calls) != 1 || images.calls[0] != want[0] {
		t.Errorf("fetched keys: got %v, want %v", images.calls, want)
	}
}

func TestLogoRejectsInvalidName(t *testing.T) {
	images := &fakeImageStore{}
	service := testBrandsServiceWithImages(images)

	_, err := service.Logo(t.Context(), &assetsv1.ImageRequest{Name: "../etc"})
	if status.Code(err) != codes.InvalidArgument {
		t.Errorf("got %v, want InvalidArgument", err)
	}
	if len(images.calls) != 0 {
		t.Errorf("image store should not be called for an invalid name, got %v", images.calls)
	}
}

func TestLogoMapsNotFound(t *testing.T) {
	images := &fakeImageStore{err: storage.ErrImageNotFound}
	service := testBrandsServiceWithImages(images)

	_, err := service.Logo(t.Context(), &assetsv1.ImageRequest{Name: "adidas"})
	if status.Code(err) != codes.NotFound {
		t.Errorf("got %v, want NotFound", err)
	}
}

func TestLogoMapsOtherErrorsToUnavailable(t *testing.T) {
	images := &fakeImageStore{err: errors.New("s3 exploded")}
	service := testBrandsServiceWithImages(images)

	_, err := service.Logo(t.Context(), &assetsv1.ImageRequest{Name: "adidas"})
	if status.Code(err) != codes.Unavailable {
		t.Errorf("got %v, want Unavailable", err)
	}
}

func TestLogoFailsWithoutConfiguredImageStore(t *testing.T) {
	service := testBrandsService(nil)

	_, err := service.Logo(t.Context(), &assetsv1.ImageRequest{Name: "adidas"})
	if status.Code(err) != codes.Unavailable {
		t.Errorf("got %v, want Unavailable", err)
	}
}
