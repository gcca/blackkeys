package handling

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/aws/aws-sdk-go-v2/service/s3"
	"github.com/bradfitz/gomemcache/memcache"
	"github.com/parquet-go/parquet-go"
	"github.com/plaza-san-miguel/blackkeys/blackkeys-assets/blackkeys"
	"github.com/plaza-san-miguel/blackkeys/blackkeys-assets/blackkeys/core"
	"github.com/plaza-san-miguel/blackkeys/blackkeys-assets/blackkeys/storage"
	assetsv1 "github.com/plaza-san-miguel/blackkeys/blackkeys-assets/gen/assetsv1"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
	"google.golang.org/protobuf/proto"
)

const brandsListCacheKey = "blackkeys-assets:brands:list:v1"
const brandsListCacheTTL = 15 * time.Minute

type brandRecord struct {
	Name        string          `parquet:"name,optional"`
	DisplayName string          `parquet:"display_name,optional"`
	LogoURL     string          `parquet:"logo_url,optional"`
	PictureURL  string          `parquet:"picture_url,optional"`
	Description string          `parquet:"description,optional"`
	IsActive    bool            `parquet:"is_active,optional"`
	KioskID     int32           `parquet:"kiosk_id,optional"`
	Amenities   []amenityRecord `parquet:"amenities,list" parquet-element:",optional"`
	Stores      []storeRecord   `parquet:"stores,list" parquet-element:",optional"`
	Tags        []string        `parquet:"tags,list" parquet-element:",optional"`
}

type amenityRecord struct {
	Name  string `parquet:"name,optional"`
	Value string `parquet:"value,optional"`
}

type storeRecord struct {
	ID   int32  `parquet:"kiosk_id,optional"`
	Name string `parquet:"display_name,optional"`
}

func (r brandRecord) brand() *assetsv1.Brand {
	amenities := make([]*assetsv1.Amenity, 0, len(r.Amenities))
	for _, entry := range r.Amenities {
		amenities = append(amenities, &assetsv1.Amenity{
			Name:  entry.Name,
			Value: entry.Value,
		})
	}

	stores := make([]*assetsv1.Store, 0, len(r.Stores))
	for _, entry := range r.Stores {
		stores = append(stores, &assetsv1.Store{
			Id:   entry.ID,
			Name: entry.Name,
		})
	}

	return &assetsv1.Brand{
		Name:        r.Name,
		DisplayName: r.DisplayName,
		LogoUrl:     r.LogoURL,
		PictureUrl:  r.PictureURL,
		Description: r.Description,
		IsActive:    r.IsActive,
		KioskId:     r.KioskID,
		Amenities:   amenities,
		Stores:      stores,
		Tags:        r.Tags,
	}
}

func decodeBrands(snapshot []byte) ([]*assetsv1.Brand, error) {
	records, err := parquet.Read[brandRecord](bytes.NewReader(snapshot), int64(len(snapshot)))
	if err != nil {
		return nil, fmt.Errorf("brands snapshot: %w", err)
	}

	brands := make([]*assetsv1.Brand, 0, len(records))
	for _, record := range records {
		brands = append(brands, record.brand())
	}
	return brands, nil
}

func LoadBrands(ctx context.Context) ([]*assetsv1.Brand, error) {
	settings, err := core.SettingsFromEnv()
	if err != nil {
		return nil, fmt.Errorf("settings: %w", err)
	}
	return loadBrands(ctx, settings)
}

func loadBrands(ctx context.Context, settings core.Settings) ([]*assetsv1.Brand, error) {
	snapshot, err := storage.FetchBrandsSnapshot(ctx, settings)
	if err != nil {
		return nil, err
	}

	return decodeBrands(snapshot)
}

type BrandsService struct {
	assetsv1.UnimplementedBrandsServer
	brands []*assetsv1.Brand
	cache  brandsCache
	images imageStore
}

type brandsCache interface {
	Get(string) (*memcache.Item, error)
	Set(*memcache.Item) error
}

// imageStore fetches a single brand image's bytes and content type by S3 key.
// It is injectable so tests never need a live bucket.
type imageStore interface {
	GetImage(ctx context.Context, key string) (data []byte, contentType string, err error)
}

// s3ImageStore is the production imageStore: a bucket name plus a single
// shared *s3.Client, built once at service construction rather than per
// request (unlike FetchBrandsSnapshot's one-shot startup fetch, Logo/Picture
// are called on every incoming request).
type s3ImageStore struct {
	client *s3.Client
	bucket string
}

func (s s3ImageStore) GetImage(ctx context.Context, key string) ([]byte, string, error) {
	return storage.FetchImage(ctx, s.client, s.bucket, key)
}

func NewBrandsService(ctx context.Context) (*BrandsService, error) {
	settings, err := core.SettingsFromEnv()
	if err != nil {
		return nil, fmt.Errorf("settings: %w", err)
	}

	cache, err := newBrandsCache(settings.CacheNodes, settings.Replication)
	if err != nil {
		return nil, err
	}

	brands, err := loadBrands(ctx, settings)
	if err != nil {
		return nil, err
	}

	client, err := storage.NewS3Client(ctx, settings)
	if err != nil {
		return nil, fmt.Errorf("images: %w", err)
	}

	return newBrandsService(brands, cache, s3ImageStore{client: client, bucket: settings.BucketName}), nil
}

func NewBrandsServiceFromSnapshot(snapshot []byte) (*BrandsService, error) {
	brands, err := decodeBrands(snapshot)
	if err != nil {
		return nil, err
	}
	return newBrandsService(brands, nil, nil), nil
}

func newBrandsService(brands []*assetsv1.Brand, cache brandsCache, images imageStore) *BrandsService {
	return &BrandsService{brands: brands, cache: cache, images: images}
}

func newBrandsCache(nodes []string, replication int) (brandsCache, error) {
	if len(nodes) == 0 {
		return nil, nil
	}
	cache, err := blackkeys.NewReplicaClient(replication, nodes...)
	if err != nil {
		return nil, fmt.Errorf("cache: %w", err)
	}
	return cache, nil
}

func (s *BrandsService) List(context.Context, *assetsv1.ListRequest) (*assetsv1.ListResponse, error) {
	if s.cache != nil {
		item, err := s.cache.Get(brandsListCacheKey)
		if err == nil {
			response := &assetsv1.ListResponse{}
			if proto.Unmarshal(item.Value, response) == nil {
				return response, nil
			}
		}
	}

	response := &assetsv1.ListResponse{Brands: s.brands}
	if s.cache != nil {
		value, err := proto.Marshal(response)
		if err == nil {
			_ = s.cache.Set(&memcache.Item{
				Key:        brandsListCacheKey,
				Value:      value,
				Expiration: int32(brandsListCacheTTL / time.Second),
			})
		}
	}
	return response, nil
}

// brandImageKey mirrors blackkeys-assets-bo's own BrandImageKey
// (handling/brand/routes/common.cpp) — the two codebases independently agree
// on this key shape; keep them identical.
func brandImageKey(name, kind string) string {
	return "brands/name=" + name + "/" + kind + ".webp"
}

// validBrandName mirrors blackkeys-assets-bo's RejectSegment: a brand name
// used as an S3 key segment must not be empty, ".", "..", contain a path
// separator, or contain a control character.
func validBrandName(name string) bool {
	if name == "" || name == "." || name == ".." {
		return false
	}
	if strings.ContainsAny(name, "/\\") {
		return false
	}
	for _, r := range name {
		if r < 0x20 || r == 0x7f {
			return false
		}
	}
	return true
}

func (s *BrandsService) image(ctx context.Context, name, kind string) (*assetsv1.ImageResponse, error) {
	if !validBrandName(name) {
		return nil, status.Error(codes.InvalidArgument, "invalid brand name")
	}
	if s.images == nil {
		return nil, status.Error(codes.Unavailable, "image store not configured")
	}

	data, contentType, err := s.images.GetImage(ctx, brandImageKey(name, kind))
	if errors.Is(err, storage.ErrImageNotFound) {
		return nil, status.Errorf(codes.NotFound, "%s not found for brand %q", kind, name)
	}
	if err != nil {
		return nil, status.Errorf(codes.Unavailable, "fetch %s: %v", kind, err)
	}
	return &assetsv1.ImageResponse{Data: data, ContentType: contentType}, nil
}

func (s *BrandsService) Logo(ctx context.Context, req *assetsv1.ImageRequest) (*assetsv1.ImageResponse, error) {
	return s.image(ctx, req.GetName(), "logo")
}

func (s *BrandsService) Picture(ctx context.Context, req *assetsv1.ImageRequest) (*assetsv1.ImageResponse, error) {
	return s.image(ctx, req.GetName(), "picture")
}
