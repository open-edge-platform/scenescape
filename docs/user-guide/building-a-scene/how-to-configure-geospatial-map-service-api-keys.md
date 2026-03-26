# How to Configure Geospatial Map Service API Keys

## API Key Configuration

The geospatial mapping functionality requires API keys for Google Maps or Mapbox. These should be configured as environment variables for security.

### Environment Variables For API Keys

| Environment Variable  | Provider    | Required                       | Description                                                    |
| --------------------- | ----------- | ------------------------------ | -------------------------------------------------------------- |
| `GOOGLE_MAPS_API_KEY` | Google Maps | Optional (choose one provider) | API key used when rendering maps through Google Maps services. |
| `MAPBOX_API_KEY`      | Mapbox      | Optional (choose one provider) | API key used when rendering maps through Mapbox services.      |

```bash
# Google Maps API Key (for Google Maps provider)
export GOOGLE_MAPS_API_KEY="your_google_maps_api_key_here"

# Mapbox API Key (for Mapbox provider)
export MAPBOX_API_KEY="your_mapbox_api_key_here"
```

**Expected output:** API key environment variables are available in the current shell session.

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

### Docker Deployment

When deploying with Docker, add the environment variables to your docker-compose.yml:

| Compose Service | Environment Variable  | Value Pattern                   |
| --------------- | --------------------- | ------------------------------- |
| `manager`       | `GOOGLE_MAPS_API_KEY` | `your_google_maps_api_key_here` |
| `manager`       | `MAPBOX_API_KEY`      | `your_mapbox_api_key_here`      |

```yaml
services:
  manager:
    environment:
      # set api key for the mapping service of choice. you need only one.
      - GOOGLE_MAPS_API_KEY=your_google_maps_api_key_here
      - MAPBOX_API_KEY=your_mapbox_api_key_here
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
