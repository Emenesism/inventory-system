package excel

import (
	"fmt"
	"io"
	"math"
	"strconv"
	"strings"

	"backend/internal/domain"

	"github.com/xuri/excelize/v2"
)

var headerAliases = map[string]string{
	"product_name":      "product_name",
	"product name":      "product_name",
	"product":           "product_name",
	"نام محصول":         "product_name",
	"نام کالا":          "product_name",
	"quantity":          "quantity",
	"qty":               "quantity",
	"تعداد":             "quantity",
	"avg_buy_price":     "avg_buy_price",
	"avg buy price":     "avg_buy_price",
	"average buy price": "avg_buy_price",
	"قیمت خرید":         "avg_buy_price",
	"قيمت خريد":         "avg_buy_price",
	"میانگین قیمت خرید": "avg_buy_price",
	"last_buy_price":    "last_buy_price",
	"last buy price":    "last_buy_price",
	"آخرین قیمت خرید":   "last_buy_price",
	"آخرين قيمت خريد":   "last_buy_price",
	"sell_price":        "sell_price",
	"sell price":        "sell_price",
	"sales price":       "sell_price",
	"قیمت فروش":         "sell_price",
	"قيمت فروش":         "sell_price",
	"alarm":             "alarm",
	"آلارم":             "alarm",
	"source":            "source",
	"منبع":              "source",
}

func ParseInventoryRows(reader io.Reader) ([]domain.InventoryImportRow, error) {
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

	colMap := mapColumns(rows[0])
	if _, ok := colMap["product_name"]; !ok {
		return nil, fmt.Errorf("missing required column: product_name")
	}
	if _, ok := colMap["quantity"]; !ok {
		return nil, fmt.Errorf("missing required column: quantity")
	}
	if _, ok := colMap["avg_buy_price"]; !ok {
		return nil, fmt.Errorf("missing required column: avg_buy_price")
	}

	result := make([]domain.InventoryImportRow, 0, len(rows)-1)
	for index := 1; index < len(rows); index++ {
		cells := rows[index]
		name := readCell(cells, colMap["product_name"])
		name = strings.TrimSpace(name)
		if name == "" {
			continue
		}

		qty, err := parseInt(readCell(cells, colMap["quantity"]))
		if err != nil {
			return nil, fmt.Errorf("row %d invalid quantity: %w", index+1, err)
		}

		avgPrice, err := parseFloat(readCell(cells, colMap["avg_buy_price"]))
		if err != nil {
			return nil, fmt.Errorf("row %d invalid avg_buy_price: %w", index+1, err)
		}

		lastPrice := avgPrice
		if idx, ok := colMap["last_buy_price"]; ok {
			raw := strings.TrimSpace(readCell(cells, idx))
			if raw != "" {
				parsed, err := parseFloat(raw)
				if err != nil {
					return nil, fmt.Errorf("row %d invalid last_buy_price: %w", index+1, err)
				}
				lastPrice = parsed
			}
		}

		sellPrice := 0.0
		if idx, ok := colMap["sell_price"]; ok {
			raw := strings.TrimSpace(readCell(cells, idx))
			if raw != "" {
				parsed, err := parseFloat(raw)
				if err != nil {
					return nil, fmt.Errorf("row %d invalid sell_price: %w", index+1, err)
				}
				sellPrice = parsed
			}
		}

		var alarm *int
		if idx, ok := colMap["alarm"]; ok {
			raw := strings.TrimSpace(readCell(cells, idx))
			if raw != "" {
				value, err := parseInt(raw)
				if err != nil {
					return nil, fmt.Errorf("row %d invalid alarm: %w", index+1, err)
				}
				alarm = &value
			}
		}

		var source *string
		if idx, ok := colMap["source"]; ok {
			value := strings.TrimSpace(readCell(cells, idx))
			if value != "" {
				source = &value
			}
		}

		result = append(result, domain.InventoryImportRow{
			ProductName:  name,
			Quantity:     qty,
			AvgBuyPrice:  avgPrice,
			LastBuyPrice: lastPrice,
			SellPrice:    sellPrice,
			Alarm:        alarm,
			Source:       source,
		})
	}

	if len(result) == 0 {
		return nil, fmt.Errorf("excel file has no valid data rows")
	}
	return result, nil
}

func mapColumns(header []string) map[string]int {
	mapped := make(map[string]int)
	for idx, col := range header {
		normalized := normalizeHeader(col)
		if normalized == "" {
			continue
		}
		canonical, ok := headerAliases[normalized]
		if !ok {
			continue
		}
		if _, exists := mapped[canonical]; !exists {
			mapped[canonical] = idx
		}
	}
	return mapped
}

func normalizeHeader(raw string) string {
	value := strings.TrimSpace(raw)
	value = strings.TrimPrefix(value, "\ufeff")
	value = strings.ToLower(value)
	value = strings.ReplaceAll(value, "_", " ")
	value = strings.Join(strings.Fields(value), " ")
	return value
}

func readCell(row []string, idx int) string {
	if idx < 0 || idx >= len(row) {
		return ""
	}
	return row[idx]
}

func parseInt(raw string) (int, error) {
	value := strings.TrimSpace(raw)
	if value == "" {
		return 0, fmt.Errorf("value is empty")
	}

	asFloat, err := strconv.ParseFloat(strings.ReplaceAll(value, ",", ""), 64)
	if err != nil {
		return 0, fmt.Errorf("not a number")
	}
	if math.Mod(asFloat, 1) != 0 {
		return 0, fmt.Errorf("must be an integer")
	}
	return int(asFloat), nil
}

func parseFloat(raw string) (float64, error) {
	value := strings.TrimSpace(raw)
	if value == "" {
		return 0, fmt.Errorf("value is empty")
	}
	parsed, err := strconv.ParseFloat(strings.ReplaceAll(value, ",", ""), 64)
	if err != nil {
		return 0, fmt.Errorf("not a number")
	}
	return parsed, nil
}
