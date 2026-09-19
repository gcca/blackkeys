package handling

import (
	"bytes"
	"context"
	"fmt"

	"github.com/parquet-go/parquet-go"
	"github.com/plaza-san-miguel/blackkeys/blackkeys-assets/blackkeys/core"
	"github.com/plaza-san-miguel/blackkeys/blackkeys-assets/blackkeys/storage"
	assetsv1 "github.com/plaza-san-miguel/blackkeys/blackkeys-assets/gen/assetsv1"
)

type storeRecord struct {
	ID          int32                 `parquet:"id"`
	Name        string                `parquet:"name"`
	DirectoryID int32                 `parquet:"directoryId"`
	IsActive    bool                  `parquet:"isActive"`
	IsNew       bool                  `parquet:"isNew"`
	Logo        string                `parquet:"logo"`
	StorePhoto  string                `parquet:"storePhoto"`
	Description string                `parquet:"description"`
	Phone       string                `parquet:"phone"`
	Website     string                `parquet:"website"`
	Facebook    string                `parquet:"facebook"`
	Instagram   string                `parquet:"instagram"`
	Tiktok      string                `parquet:"tiktok"`
	Subcategory subcategoryRecord     `parquet:"subcategory"`
	Stores      []storeLocationRecord `parquet:"stores"`
}

type subcategoryRecord struct {
	ID       int32          `parquet:"id"`
	Name     string         `parquet:"name"`
	Category categoryRecord `parquet:"category"`
}

type categoryRecord struct {
	ID   int32  `parquet:"id"`
	Name string `parquet:"name"`
}

type storeLocationRecord struct {
	Location locationRecord `parquet:"location"`
}

type locationRecord struct {
	ID   int32  `parquet:"id"`
	Name string `parquet:"name"`
}

func (r storeRecord) store() *assetsv1.Store {
	locations := make([]*assetsv1.StoreLocation, 0, len(r.Stores))
	for _, entry := range r.Stores {
		locations = append(locations, &assetsv1.StoreLocation{
			Location: &assetsv1.Location{
				Id:   entry.Location.ID,
				Name: entry.Location.Name,
			},
		})
	}

	return &assetsv1.Store{
		Id:          r.ID,
		Name:        r.Name,
		DirectoryId: r.DirectoryID,
		IsActive:    r.IsActive,
		IsNew:       r.IsNew,
		Logo:        r.Logo,
		StorePhoto:  r.StorePhoto,
		Description: r.Description,
		Phone:       r.Phone,
		Website:     r.Website,
		Facebook:    r.Facebook,
		Instagram:   r.Instagram,
		Tiktok:      r.Tiktok,
		Subcategory: &assetsv1.Subcategory{
			Id:   r.Subcategory.ID,
			Name: r.Subcategory.Name,
			Category: &assetsv1.Category{
				Id:   r.Subcategory.Category.ID,
				Name: r.Subcategory.Category.Name,
			},
		},
		Stores: locations,
	}
}

func decodeStores(snapshot []byte) ([]*assetsv1.Store, error) {
	records, err := parquet.Read[storeRecord](bytes.NewReader(snapshot), int64(len(snapshot)))
	if err != nil {
		return nil, fmt.Errorf("stores snapshot: %w", err)
	}

	stores := make([]*assetsv1.Store, 0, len(records))
	for _, record := range records {
		stores = append(stores, record.store())
	}
	return stores, nil
}

func LoadStores(ctx context.Context) ([]*assetsv1.Store, error) {
	settings, err := core.SettingsFromEnv()
	if err != nil {
		return nil, fmt.Errorf("settings: %w", err)
	}

	snapshot, err := storage.FetchStoresSnapshot(ctx, settings)
	if err != nil {
		return nil, err
	}

	return decodeStores(snapshot)
}

type StoresService struct {
	assetsv1.UnimplementedStoresServer
	stores []*assetsv1.Store
}

func NewStoresService(ctx context.Context) (*StoresService, error) {
	stores, err := LoadStores(ctx)
	if err != nil {
		return nil, err
	}
	return &StoresService{stores: stores}, nil
}

func NewStoresServiceFromSnapshot(snapshot []byte) (*StoresService, error) {
	stores, err := decodeStores(snapshot)
	if err != nil {
		return nil, err
	}
	return &StoresService{stores: stores}, nil
}

func (s *StoresService) List(context.Context, *assetsv1.ListRequest) (*assetsv1.ListResponse, error) {
	return &assetsv1.ListResponse{Stores: s.stores}, nil
}
