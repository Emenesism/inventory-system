package excel

import (
	"bytes"
	"encoding/csv"
	"fmt"
	"io"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"

	"backend/internal/domain"

	"github.com/xuri/excelize/v2"
)

const (
	optionSeparator = "، "
	labelColor      = "رنگ"
	labelSize       = "سایز"
	labelFont       = "فونت"
	labelModel      = "مدل"
)

var (
	persianDigitsReplacer = strings.NewReplacer(
		"۰", "0",
		"۱", "1",
		"۲", "2",
		"۳", "3",
		"۴", "4",
		"۵", "5",
		"۶", "6",
		"۷", "7",
		"۸", "8",
		"۹", "9",
	)
	arabicDigitsReplacer = strings.NewReplacer(
		"٠", "0",
		"١", "1",
		"٢", "2",
		"٣", "3",
		"٤", "4",
		"٥", "5",
		"٦", "6",
		"٧", "7",
		"٨", "8",
		"٩", "9",
	)
	arabicToPersianLetters = strings.NewReplacer(
		"ي", "ی",
		"ك", "ک",
		"ة", "ه",
		"ۀ", "ه",
		"ؤ", "و",
		"أ", "ا",
		"إ", "ا",
		"ٱ", "ا",
		"آ", "ا",
		"ئ", "ی",
	)
	sizeDigitsPattern = regexp.MustCompile(`^[0-9]{1,3}$`)
	sizeTokenPattern  = regexp.MustCompile(`^(x{0,3}l|xl|xxl|xxxl|\d+xl|xs|s|m|l)$`)
	colorCodePattern  = regexp.MustCompile(`#\w{3,6}`)
	fontValueSet      = map[string]struct{}{}

	extraColorWords = []string{
		"طلایی",
		"نقره ای",
		"نقره‌ای",
		"برنزی",
		"برنز",
		"زرشکی",
		"یاسی",
		"کرم",
		"نارنجی",
		"صورتی",
		"قهوه ای",
		"قهوه‌ای",
		"سرمه ای",
		"سرمه‌ای",
		"سبز ارتشی",
		"سبز تیره",
		"آبی نفتی",
		"آبی تیره",
		"سفید قرمز",
		"سفید مشکی",
		"سبز دیجیتال",
		"خاکی دیجیتال",
		"سیمانی دیجیتال",
		"مشکی خاکی",
		"مولتی کم خاکی",
		"مولتی‌کم خاکی",
		"نخودی",
		"نخودی روشن",
		"خردلی",
		"طوسی روشن",
		"طوسی تیره",
		"مشکی",
		"سفید",
		"قرمز",
		"سبز",
		"خاکی",
		"سرمه",
		"آبی",
		"طوسی",
		"قهوه",
	}
	extraSizeValues = []string{
		"XS",
		"S",
		"M",
		"L",
		"XL",
		"XXL",
		"XXXL",
		"2XL",
		"3XL",
		"4XL",
		"5XL",
		"ایکس لارج",
		"لارج",
		"مدیوم",
		"اسمال",
		"فری",
		"فری سایز",
		"سایز فری",
		"وان سایز",
	}
	normalizedColorWords = normalizeValueList(extraColorWords)
	normalizedSizeValues = normalizeValueSet(extraSizeValues)
)

type rawProductRow struct {
	rowNumber     int
	title         string
	priceRaw      string
	optionName1   string
	optionValues1 string
	optionName2   string
	optionValues2 string
}

func ParseProductPriceRows(
	fileName string,
	reader io.Reader,
) ([]domain.ProductPriceRow, string, error) {
	data, err := io.ReadAll(reader)
	if err != nil {
		return nil, "", fmt.Errorf("read file: %w", err)
	}
	if len(data) == 0 {
		return nil, "", fmt.Errorf("input file is empty")
	}

	ext := strings.ToLower(strings.TrimSpace(filepath.Ext(fileName)))
	switch ext {
	case ".csv":
		rows, parseErr := parseCSVRows(data)
		if parseErr != nil {
			return nil, "", parseErr
		}
		items, mode, parseErr := parseProductPriceTable(rows)
		if parseErr != nil {
			return nil, "", parseErr
		}
		return items, mode, nil
	case ".xlsx", ".xlsm", ".xls":
		rows, parseErr := parseExcelRows(data)
		if parseErr != nil {
			return nil, "", parseErr
		}
		items, mode, parseErr := parseProductPriceTable(rows)
		if parseErr != nil {
			return nil, "", parseErr
		}
		return items, mode, nil
	default:
		excelRows, excelErr := parseExcelRows(data)
		if excelErr == nil {
			if items, mode, parseErr := parseProductPriceTable(excelRows); parseErr == nil {
				return items, mode, nil
			}
		}
		csvRows, csvErr := parseCSVRows(data)
		if csvErr == nil {
			if items, mode, parseErr := parseProductPriceTable(csvRows); parseErr == nil {
				return items, mode, nil
			}
		}
		return nil, "", fmt.Errorf("unsupported or invalid price file format")
	}
}

func parseCSVRows(data []byte) ([][]string, error) {
	reader := csv.NewReader(bytes.NewReader(data))
	reader.FieldsPerRecord = -1
	reader.LazyQuotes = true
	rows, err := reader.ReadAll()
	if err != nil {
		return nil, fmt.Errorf("read csv rows: %w", err)
	}
	if len(rows) == 0 {
		return nil, fmt.Errorf("csv file is empty")
	}
	return rows, nil
}

func parseExcelRows(data []byte) ([][]string, error) {
	file, err := excelize.OpenReader(bytes.NewReader(data))
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
	return rows, nil
}

func parseProductPriceTable(
	rows [][]string,
) ([]domain.ProductPriceRow, string, error) {
	if len(rows) == 0 {
		return nil, "", fmt.Errorf("input file is empty")
	}

	header := rows[0]
	directMap := mapDirectPriceColumns(header)
	if hasRequiredColumns(directMap, "product_name", "price") {
		parsed, err := parseDirectPriceRows(rows, directMap)
		if err != nil {
			return nil, "", err
		}
		return uniquePriceRows(parsed), "direct", nil
	}

	rawMap := mapRawOptionColumns(header)
	if hasRequiredColumns(rawMap, "title", "price") {
		parsed, err := parseRawOptionPriceRows(rows, rawMap)
		if err != nil {
			return nil, "", err
		}
		if len(parsed) > 0 {
			return uniquePriceRows(parsed), "options", nil
		}
		return nil, "", fmt.Errorf("file has no valid option-based price rows")
	}

	return nil, "", fmt.Errorf("missing required columns: product_name+price or title+price")
}

func parseDirectPriceRows(
	rows [][]string,
	colMap map[string]int,
) ([]domain.ProductPriceRow, error) {
	result := make([]domain.ProductPriceRow, 0, len(rows)-1)
	nameIndex := colMap["product_name"]
	priceIndex := colMap["price"]

	for index := 1; index < len(rows); index++ {
		cells := rows[index]
		name := cleanText(readCell(cells, nameIndex))
		if name == "" {
			continue
		}
		rawPrice := cleanText(readCell(cells, priceIndex))
		if rawPrice == "" {
			continue
		}
		price, err := parsePriceValue(rawPrice)
		if err != nil {
			return nil, fmt.Errorf("row %d invalid price: %w", index+1, err)
		}
		result = append(result, domain.ProductPriceRow{
			ProductName: name,
			Price:       price,
		})
	}
	if len(result) == 0 {
		return nil, fmt.Errorf("file has no valid direct price rows")
	}
	return result, nil
}

func parseRawOptionPriceRows(
	rows [][]string,
	colMap map[string]int,
) ([]domain.ProductPriceRow, error) {
	rawRows := make([]rawProductRow, 0, len(rows)-1)
	for index := 1; index < len(rows); index++ {
		cells := rows[index]
		row := rawProductRow{
			rowNumber:     index + 1,
			title:         cleanText(readCell(cells, colMap["title"])),
			priceRaw:      cleanText(readCell(cells, colMap["price"])),
			optionName1:   cleanText(readOptionalCell(cells, colMap, "option_name1")),
			optionValues1: cleanText(readOptionalCell(cells, colMap, "option_values1")),
			optionName2:   cleanText(readOptionalCell(cells, colMap, "option_name2")),
			optionValues2: cleanText(readOptionalCell(cells, colMap, "option_values2")),
		}
		if row.title == "" && row.priceRaw == "" && row.optionValues1 == "" && row.optionValues2 == "" {
			continue
		}
		rawRows = append(rawRows, row)
	}
	if len(rawRows) == 0 {
		return nil, fmt.Errorf("file has no usable data rows")
	}

	type productGroup struct {
		title string
		rows  []rawProductRow
	}
	groups := make([]productGroup, 0)
	currentTitle := ""
	currentRows := make([]rawProductRow, 0)
	flush := func() {
		if currentTitle == "" || len(currentRows) == 0 {
			return
		}
		groups = append(groups, productGroup{title: currentTitle, rows: append([]rawProductRow(nil), currentRows...)})
	}

	for _, row := range rawRows {
		if row.title != "" {
			flush()
			currentTitle = row.title
			currentRows = []rawProductRow{row}
			continue
		}
		if currentTitle == "" {
			continue
		}
		currentRows = append(currentRows, row)
	}
	flush()

	if len(groups) == 0 {
		return nil, fmt.Errorf("file has no titled products")
	}

	result := make([]domain.ProductPriceRow, 0)
	for _, group := range groups {
		generated, err := generateCleanNames(group.title, group.rows)
		if err != nil {
			return nil, err
		}
		result = append(result, generated...)
	}
	return result, nil
}

func generateCleanNames(
	title string,
	rows []rawProductRow,
) ([]domain.ProductPriceRow, error) {
	if len(rows) == 0 {
		return nil, nil
	}
	baseRow := rows[0]
	basePrice := 0.0
	if baseRow.priceRaw != "" {
		parsed, err := parsePriceValue(baseRow.priceRaw)
		if err != nil {
			return nil, fmt.Errorf("row %d invalid price: %w", baseRow.rowNumber, err)
		}
		basePrice = parsed
	}

	baseLabel1 := cleanLabel(baseRow.optionName1)
	baseLabel2 := cleanLabel(baseRow.optionName2)
	baseValues1 := splitValues(baseRow.optionValues1)
	baseValues2 := splitValues(baseRow.optionValues2)

	label1 := baseLabel1
	if label1 == "" && len(baseValues1) > 0 {
		label1 = detectLabel(baseValues1, baseRow.optionValues1)
	}

	label2 := baseLabel2
	if label2 == "" && len(baseValues2) > 0 {
		label2 = detectLabel(baseValues2, baseRow.optionValues2)
	}

	output := make([]domain.ProductPriceRow, 0)
	if len(rows) > 1 {
		for _, row := range rows[1:] {
			rowPrice := basePrice
			if row.priceRaw != "" {
				parsed, err := parsePriceValue(row.priceRaw)
				if err != nil {
					return nil, fmt.Errorf("row %d invalid price: %w", row.rowNumber, err)
				}
				rowPrice = parsed
			}
			values1 := splitValues(row.optionValues1)
			values2 := splitValues(row.optionValues2)
			if len(values1) == 0 && len(values2) == 0 {
				continue
			}
			for _, pair := range expandValues(values1, values2) {
				output = append(output, domain.ProductPriceRow{
					ProductName: buildCleanName(title, label1, pair[0], label2, pair[1]),
					Price:       rowPrice,
				})
			}
		}
		if len(output) > 0 {
			return output, nil
		}
	}

	if len(baseValues1) > 0 || len(baseValues2) > 0 {
		for _, pair := range expandValues(baseValues1, baseValues2) {
			output = append(output, domain.ProductPriceRow{
				ProductName: buildCleanName(title, label1, pair[0], label2, pair[1]),
				Price:       basePrice,
			})
		}
		return output, nil
	}

	return []domain.ProductPriceRow{{
		ProductName: title,
		Price:       basePrice,
	}}, nil
}

func mapDirectPriceColumns(header []string) map[string]int {
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
		"unit price":   "price",
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

func mapRawOptionColumns(header []string) map[string]int {
	aliases := map[string]string{
		"title":                   "title",
		"نام":                     "title",
		"عنوان":                   "title",
		"نام کالا":                "title",
		"نام محصول":               "title",
		"price":                   "price",
		"sell_price":              "price",
		"sell price":              "price",
		"sales price":             "price",
		"unit price":              "price",
		"قیمت":                    "price",
		"قيمت":                    "price",
		"قیمت فروش":               "price",
		"قيمت فروش":               "price",
		"productoptionname1":      "option_name1",
		"product option name1":    "option_name1",
		"product option name 1":   "option_name1",
		"optionname1":             "option_name1",
		"option name1":            "option_name1",
		"option name 1":           "option_name1",
		"productoptionvalues1":    "option_values1",
		"product option values1":  "option_values1",
		"product option values 1": "option_values1",
		"optionvalues1":           "option_values1",
		"option values1":          "option_values1",
		"option values 1":         "option_values1",
		"productoptionname2":      "option_name2",
		"product option name2":    "option_name2",
		"product option name 2":   "option_name2",
		"optionname2":             "option_name2",
		"option name2":            "option_name2",
		"option name 2":           "option_name2",
		"productoptionvalues2":    "option_values2",
		"product option values2":  "option_values2",
		"product option values 2": "option_values2",
		"optionvalues2":           "option_values2",
		"option values2":          "option_values2",
		"option values 2":         "option_values2",
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

func hasRequiredColumns(colMap map[string]int, required ...string) bool {
	for _, key := range required {
		if _, ok := colMap[key]; !ok {
			return false
		}
	}
	return true
}

func readOptionalCell(cells []string, colMap map[string]int, key string) string {
	idx, ok := colMap[key]
	if !ok {
		return ""
	}
	return readCell(cells, idx)
}

func parsePriceValue(raw string) (float64, error) {
	value := normalizeNumericValue(raw)
	if value == "" {
		return 0, fmt.Errorf("value is empty")
	}
	parsed, err := strconv.ParseFloat(value, 64)
	if err != nil {
		return 0, fmt.Errorf("not a number")
	}
	if parsed < 0 {
		return 0, fmt.Errorf("price cannot be negative")
	}
	return parsed, nil
}

func normalizeNumericValue(raw string) string {
	value := strings.TrimSpace(raw)
	value = strings.TrimPrefix(value, "\ufeff")
	value = persianDigitsReplacer.Replace(value)
	value = arabicDigitsReplacer.Replace(value)
	value = strings.ReplaceAll(value, "٬", "")
	value = strings.ReplaceAll(value, ",", "")
	value = strings.ReplaceAll(value, "،", "")
	value = strings.ReplaceAll(value, "٫", ".")
	return strings.TrimSpace(value)
}

func cleanText(value string) string {
	text := strings.TrimSpace(value)
	if text == "" {
		return ""
	}
	return strings.Join(strings.Fields(text), " ")
}

func cleanLabel(value string) string {
	label := cleanText(value)
	label = strings.TrimSuffix(label, ":")
	return cleanText(label)
}

func splitValues(raw string) []string {
	raw = cleanText(raw)
	if raw == "" {
		return nil
	}
	parts := make([]string, 0)
	buf := make([]rune, 0, len(raw))
	depth := 0
	flush := func() {
		if len(buf) == 0 {
			return
		}
		part := strings.TrimSpace(string(buf))
		buf = buf[:0]
		if part == "" {
			return
		}
		if idx := strings.Index(part, ":"); idx >= 0 {
			part = strings.TrimSpace(part[:idx])
		}
		part = cleanText(part)
		if part != "" {
			parts = append(parts, part)
		}
	}

	for _, ch := range raw {
		switch ch {
		case '(':
			depth++
		case ')':
			if depth > 0 {
				depth--
			}
		}
		if (ch == ',' || ch == '،') && depth == 0 {
			flush()
			continue
		}
		buf = append(buf, ch)
	}
	flush()
	return parts
}

func detectLabel(values []string, raw string) string {
	normalizedRaw := strings.ToLower(strings.TrimSpace(raw))
	if colorCodePattern.MatchString(normalizedRaw) || strings.Contains(normalizedRaw, "rgb") {
		return labelColor
	}
	if looksLikeColor(values) {
		return labelColor
	}
	if looksLikeSize(values) {
		return labelSize
	}
	if looksLikeFont(values) {
		return labelFont
	}
	return labelModel
}

func looksLikeColor(values []string) bool {
	for _, value := range values {
		normalizedValue := normalizeLookupName(value)
		if normalizedValue == "" {
			continue
		}
		for _, color := range normalizedColorWords {
			if color != "" && strings.Contains(normalizedValue, color) {
				return true
			}
		}
	}
	return false
}

func looksLikeSize(values []string) bool {
	for _, value := range values {
		normalizedValue := normalizeLookupName(value)
		if normalizedValue == "" {
			continue
		}
		if _, ok := normalizedSizeValues[normalizedValue]; ok {
			return true
		}
		if sizeDigitsPattern.MatchString(normalizedValue) {
			return true
		}
		if sizeTokenPattern.MatchString(normalizedValue) {
			return true
		}
	}
	return false
}

func looksLikeFont(values []string) bool {
	for _, value := range values {
		normalizedValue := normalizeLookupName(value)
		if _, ok := fontValueSet[normalizedValue]; ok {
			return true
		}
	}
	return false
}

func expandValues(values1, values2 []string) [][2]string {
	pairs := make([][2]string, 0)
	if len(values1) > 0 && len(values2) > 0 {
		for _, value1 := range values1 {
			for _, value2 := range values2 {
				pairs = append(pairs, [2]string{value1, value2})
			}
		}
		return pairs
	}
	if len(values1) > 0 {
		for _, value1 := range values1 {
			pairs = append(pairs, [2]string{value1, ""})
		}
		return pairs
	}
	if len(values2) > 0 {
		for _, value2 := range values2 {
			pairs = append(pairs, [2]string{"", value2})
		}
		return pairs
	}
	return [][2]string{{"", ""}}
}

func buildCleanName(
	title string,
	label1 string,
	value1 string,
	label2 string,
	value2 string,
) string {
	parts := make([]string, 0, 2)
	if value1 != "" {
		label := label1
		if label == "" {
			label = labelModel
		}
		parts = append(parts, fmt.Sprintf("%s: %s", label, value1))
	}
	if value2 != "" {
		label := label2
		if label == "" {
			label = labelModel
		}
		parts = append(parts, fmt.Sprintf("%s: %s", label, value2))
	}
	if len(parts) == 0 {
		return cleanText(title)
	}
	return cleanText(title + " " + strings.Join(parts, optionSeparator))
}

func uniquePriceRows(rows []domain.ProductPriceRow) []domain.ProductPriceRow {
	seen := make(map[string]struct{}, len(rows))
	result := make([]domain.ProductPriceRow, 0, len(rows))
	for _, row := range rows {
		name := cleanText(row.ProductName)
		if name == "" {
			continue
		}
		key := normalizeLookupName(name) + "|" + strconv.FormatFloat(row.Price, 'f', 4, 64)
		if _, exists := seen[key]; exists {
			continue
		}
		seen[key] = struct{}{}
		result = append(result, domain.ProductPriceRow{
			ProductName: name,
			Price:       row.Price,
		})
	}
	return result
}

func normalizeLookupName(value string) string {
	text := normalizeNumericValue(value)
	text = arabicToPersianLetters.Replace(text)
	replacements := strings.NewReplacer(
		"،", " ",
		",", " ",
		"؛", " ",
		";", " ",
		":", " ",
		".", " ",
		"ـ", " ",
		"‌", " ",
		"\u200c", " ",
		"\u200d", " ",
	)
	text = replacements.Replace(text)
	text = strings.Join(strings.Fields(text), " ")
	return strings.ToLower(strings.TrimSpace(text))
}

func normalizeValueList(values []string) []string {
	result := make([]string, 0, len(values))
	for _, value := range values {
		normalized := normalizeLookupName(value)
		if normalized == "" {
			continue
		}
		result = append(result, normalized)
	}
	return result
}

func normalizeValueSet(values []string) map[string]struct{} {
	result := make(map[string]struct{}, len(values))
	for _, value := range values {
		normalized := normalizeLookupName(value)
		if normalized == "" {
			continue
		}
		result[normalized] = struct{}{}
	}
	return result
}
