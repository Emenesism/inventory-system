package excel

import (
	"fmt"
	"io"
	"strings"

	"github.com/xuri/excelize/v2"
)

type ProductPriceRow struct {
	ProductName string
	Price       float64
}

func ParseProductPriceRows(reader io.Reader) ([]ProductPriceRow, error) {
	file, err := excelize.OpenReader(reader)
	if err != nil {
		return nil, fmt.Errorf("open excel file: %w", err)
	}
	defer file.Close()

	sheets := file.GetSheetList()
	if len(sheets) == 0 {
		return nil, fmt.Errorf("excel file has no sheets")
	}

	rows, err := file.GetRows(sheets[0])
	if err != nil {
		return nil, fmt.Errorf("read sheet rows: %w", err)
	}
	if len(rows) == 0 {
		return nil, fmt.Errorf("excel file is empty")
	}

	colMap := mapPriceColumns(rows[0])
	nameIndex, hasName := colMap["product_name"]
	priceIndex, hasPrice := colMap["price"]
	if !hasName {
		return nil, fmt.Errorf("missing required column: product_name")
	}
	if !hasPrice {
		return nil, fmt.Errorf("missing required column: price")
	}

	result := make([]ProductPriceRow, 0, len(rows)-1)
	for index := 1; index < len(rows); index++ {
		cells := rows[index]
		name := strings.TrimSpace(readCell(cells, nameIndex))
		if name == "" {
			continue
		}
		rawPrice := strings.TrimSpace(readCell(cells, priceIndex))
		if rawPrice == "" {
			continue
		}
		price, err := parseFloat(rawPrice)
		if err != nil {
			return nil, fmt.Errorf("row %d invalid price: %w", index+1, err)
		}
		result = append(result, ProductPriceRow{
			ProductName: name,
			Price:       price,
		})
	}

	if len(result) == 0 {
		return nil, fmt.Errorf("excel file has no valid price rows")
	}
	return result, nil
}

func mapPriceColumns(header []string) map[string]int {
	aliases := map[string]string{
		"product_name": "product_name",
		"product name": "product_name",
		"product":      "product_name",
		"name":         "product_name",
		"نام کالا":     "product_name",
		"نام محصول":    "product_name",
		"price":        "price",
		"sell_price":   "price",
		"sell price":   "price",
		"sales price":  "price",
		"قیمت":         "price",
		"قيمت":         "price",
		"قیمت فروش":    "price",
		"قيمت فروش":    "price",
	}
	mapped := make(map[string]int)
	for idx, col := range header {
		normalized := normalizeHeader(col)
		if normalized == "" {
			continue
		}
		canonical, ok := aliases[normalized]
		if !ok {
			continue
		}
		if _, exists := mapped[canonical]; !exists {
			mapped[canonical] = idx
		}
	}
	return mapped
}
