package handling

import (
	"context"
	_ "embed"
	"encoding/json"
	"fmt"

	assetsv1 "github.com/plaza-san-miguel/blackkeys/blackkeys-assets/gen/assetsv1"
)

//go:embed stores.json
var storesSnapshot []byte

type storeRecord struct {
	ID          int32                 `json:"id"`
	Name        string                `json:"name"`
	DirectoryID int32                 `json:"directoryId"`
	IsActive    bool                  `json:"isActive"`
	IsNew       bool                  `json:"isNew"`
	Logo        string                `json:"logo"`
	StorePhoto  string                `json:"storePhoto"`
	Description string                `json:"description"`
	Phone       string                `json:"phone"`
	Website     string                `json:"website"`
	Facebook    string                `json:"facebook"`
	Instagram   string                `json:"instagram"`
	Tiktok      string                `json:"tiktok"`
	Subcategory subcategoryRecord     `json:"subcategory"`
	Stores      []storeLocationRecord `json:"stores"`
}

type subcategoryRecord struct {
	ID       int32          `json:"id"`
	Name     string         `json:"name"`
	Category categoryRecord `json:"category"`
}

type categoryRecord struct {
	ID   int32  `json:"id"`
	Name string `json:"name"`
}

type storeLocationRecord struct {
	Location locationRecord `json:"location"`
}

type locationRecord struct {
	ID   int32  `json:"id"`
	Name string `json:"name"`
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

func LoadStores() ([]*assetsv1.Store, error) {
	var records []storeRecord
	if err := json.Unmarshal(storesSnapshot, &records); err != nil {
		return nil, fmt.Errorf("stores snapshot: %w", err)
	}

	stores := make([]*assetsv1.Store, 0, len(records))
	for _, record := range records {
		stores = append(stores, record.store())
	}
	return stores, nil
}

type StoresService struct {
	assetsv1.UnimplementedStoresServer
	stores []*assetsv1.Store
}

func NewStoresService() (*StoresService, error) {
	stores, err := LoadStores()
	if err != nil {
		return nil, err
	}
	return &StoresService{stores: stores}, nil
}

func (s *StoresService) List(context.Context, *assetsv1.ListRequest) (*assetsv1.ListResponse, error) {
	return &assetsv1.ListResponse{Stores: s.stores}, nil
}
