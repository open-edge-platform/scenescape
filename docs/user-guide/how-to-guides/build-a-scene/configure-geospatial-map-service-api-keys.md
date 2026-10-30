# Configure Geospatial Map Service API Keys

## API Key Configuration

The geospatial mapping functionality requires API keys for Google Maps or Mapbox. The OpenStreetMap-based [auto-ROI generation feature](./configure-spatial-analytics.md#auto-generate-rois-from-openstreetmap-geospatial-scenes) requires a separate OpenStreetMap (ohsome API) key. These should be configured as environment variables for security.

### Environment Variables For API Keys

```bash
# Google Maps API Key (for Google Maps provider)
export GOOGLE_MAPS_API_KEY="your_google_maps_api_key_here"

# Mapbox API Key (for Mapbox provider)
export MAPBOX_API_KEY="your_mapbox_api_key_here"

# OpenStreetMap API Key (for the "Suggest ROIs with OSM" auto-ROI feature)
export OHSOME_API_KEY="your_ohsome_api_key_here"
```

### Getting API Keys

#### Google Maps API Key

1. Go to [Google Cloud Console](https://console.cloud.google.com/).
2. Create a new project or select an existing one.
3. Enable the following APIs:
   - Maps JavaScript API
   - Maps Static API
   - Geocoding API
4. Create credentials → API Key.
5. Restrict the API key to your domain for security.

#### Mapbox API Key

1. Go to [Mapbox Account](https://console.mapbox.com/).
2. Create an account or sign in.
3. Go to the Access Tokens section.
4. Create a new token or use the default public token.
5. Ensure it has the required scopes for your use case.

#### OpenStreetMap (ohsome) API Key

1. Sign up for a free key at [HeiGIT's ohsome account portal](https://account.heigit.org/signup).
2. Set it as the `OHSOME_API_KEY` environment variable. Without it, the `Suggest ROIs with OSM` button is disabled.

Optionally, set `OSM_MAX_ROI_FEATURES` to change the maximum number of OpenStreetMap ways processed per query (default `200`, allowed range `1`–`1000`). Queries returning more ways fail with a request to select a smaller area. Invalid values fall back to the default.

### Docker Deployment

When deploying with Docker, add the environment variables to your docker-compose.yml:

```yaml
services:
  manager:
    environment:
      # set api key for the mapping service of choice. you need only one.
      - GOOGLE_MAPS_API_KEY=your_google_maps_api_key_here
      - MAPBOX_API_KEY=your_mapbox_api_key_here
      # required only to use the OSM auto-ROI generation feature
      - OHSOME_API_KEY=your_ohsome_api_key_here
      # optional cap on OpenStreetMap ways per query (default 200, max 1000)
      - OSM_MAX_ROI_FEATURES=200
```

### Security Notes

- **Never commit API keys to source code**
- Use environment variables for all deployments
- Restrict API keys to specific domains/IPs when possible
- Rotate API keys regularly
- Monitor API usage for unexpected spikes

### Troubleshooting

If maps are not loading:

1. Check browser console for API key errors
2. Verify environment variables are set correctly
3. Ensure API keys have proper permissions/scopes
4. Check API quotas and billing (for Google Maps)
